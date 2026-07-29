import os
import zlib
import base64
import urllib.request
import urllib.error

def generate_kroki_url(diagram_type, text):
    try:
        compressed = zlib.compress(text.encode('utf-8'), 9)
        encoded = base64.urlsafe_b64encode(compressed).decode('ascii')
        return f"https://kroki.io/{diagram_type}/png/{encoded}"
    except Exception as e:
        print(f"Error encoding: {e}")
        return None

def save_image(url, filename):
    if not url: return
    try:
        # User-agent might be required by some APIs, but Kroki usually allows standard ones.
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(filename, 'wb') as out_file:
            out_file.write(response.read())
        print(f"Saved: {filename}")
    except Exception as e:
        print(f"Error downloading {filename}: {url} -> {e}")

diagrams = {
    # 1. Class Diagram (Mermaid)
    "1_Class_Diagram.png": ("mermaid", """
classDiagram
    class EligibleVoter {
        +String voter_id
        +String name
        +String email
        +String phone
        +int is_registered
    }
    class Voter {
        +String voter_id
        +String face_embedding
        +DateTime registered_at
    }
    class OTPCode {
        +String voter_id
        +String purpose
        +String code
        +DateTime expires_at
    }
    class Election {
        +int id
        +String title
        +DateTime start_at
        +DateTime end_at
        +int is_active
    }
    class Candidate {
        +int id
        +int election_id
        +String name
        +String description
    }
    class Vote {
        +int id
        +int election_id
        +String voter_id
        +int candidate_id
        +DateTime voted_at
    }
    Election "1" *-- "many" Candidate : contains
    Election "1" o-- "many" Vote : receives
    Voter "1" *-- "many" Vote : casts
    EligibleVoter "1" --> "1" Voter : registers as
    """),

    # 2. Object Diagram (PlantUML)
    "2_Object_Diagram.png": ("plantuml", """
@startuml
object "election1 : Election" as e1 {
  id = 101
  title = "Student Council 2026"
  is_active = 1
}
object "voter1 : Voter" as v1 {
  voter_id = "V001"
}
object "alice : Candidate" as c1 {
  id = 5
  name = "Alice Smith"
}
object "bob : Candidate" as c2 {
  id = 6
  name = "Bob Jones"
}
e1 *-- c1
e1 *-- c2
v1 --> e1 : votes in
@enduml
    """),

    # 3. State Diagram (Mermaid)
    "3_State_Diagram.png": ("mermaid", """
stateDiagram-v2
    [*] --> Pending : Enter Voter ID
    Pending --> OTP_Sent : Valid Eligible Voter
    OTP_Sent --> VerifiedOTP : OTP Validated
    VerifiedOTP --> VerifyingFace : Face Captured
    VerifyingFace --> VoterRegistered : Match Success
    VerifyingFace --> VerifiedOTP : Match Failed
    VoterRegistered --> [*]
    """),

    # 4. Activity Diagram (PlantUML)
    "4_Activity_Diagram.png": ("plantuml", """
@startuml
start
:Enter Voter ID;
if (Is Eligible?) then (yes)
  :Send OTP via Email;
  :Enter OTP;
  if (OTP Valid?) then (yes)
    :Capture Face;
    :Verify Face Embedding;
    if (Face Matched?) then (yes)
      :Cast Vote;
      :Save to DB;
    else (no)
      :Reject Face;
    endif
  else (no)
    :Reject OTP;
  endif
else (no)
  :Reject User;
endif
stop
@enduml
    """),

    # 5. Sequence Diagram (Mermaid)
    "5_Sequence_Diagram.png": ("mermaid", """
sequenceDiagram
    actor V as Voter
    participant App as Flask App
    participant DB as SQLite DB
    participant E as Resend API
    participant F as Face Utils
    
    V->>App: Request Vote (Voter ID)
    App->>DB: Check Eligibility
    DB-->>App: OK
    App->>E: generate_otp() & Send Email
    E-->>V: Delivers OTP
    V->>App: Submit OTP
    App->>DB: Verify OTP
    DB-->>App: Valid
    V->>App: Capture & Send Face Image
    App->>F: get_embedding_from_bgr()
    F-->>App: Vector
    App->>DB: Compare Distance
    DB-->>App: Verified
    V->>App: Select Candidate & Submit
    App->>DB: INSERT INTO votes...
    DB-->>App: Success
    App-->>V: Vote Recorded
    """),

    # 6. Collaboration Diagram (PlantUML Communication Diagram)
    "6_Collaboration_Diagram.png": ("plantuml", """
@startuml
allowmixing
actor Voter
component App
component DB
component Resend
component FaceSystem

Voter -- App : 1. Submit ID
App -- DB : 2. Check Voter
App -- Resend : 3. Request OTP
Resend -- Voter : 4. Send Email
Voter -- App : 5. Enter OTP & Face
App -- FaceSystem : 6. Verify Face
App -- DB : 7. Record Action
@enduml
    """),

    # 7. Data Flow Diagram (Mermaid Flowchart)
    "7_Data_Flow_Diagram.png": ("mermaid", """
flowchart TD
    ext_voter((Voter)) -->|Voter ID, Email| p1((Process: Auth))
    p1 -->|Query| d1[(DB: eligible_voters)]
    p1 -->|Send Request| ext_email((Resend API))
    ext_email -->|OTP| ext_voter
    ext_voter -->|OTP + Face| p2((Process: Verify))
    p2 <-->|Read/Update| d2[(DB: otp_codes)]
    p2 -->|Extract Feature| p3((Process: FaceRec))
    p2 <-->|Read| d3[(DB: voters)]
    ext_voter -->|Candidate ID| p4((Process: Vote Casting))
    p4 -->|Insert Vote| d4[(DB: votes)]
    p4 <-->|Verify Election| d5[(DB: elections)]
    """),

    # 8. Deployment Diagram (PlantUML)
    "8_Deployment_Diagram.png": ("plantuml", """
@startuml
node "Client Browser" {
  component "Web UI (HTML/JS/CSS)"
}
node "Web Server (Host)" {
  component "Flask App (app.py)"
  component "Face Utils (Facenet)"
  database "SQLite (securevote.db)"
}
cloud "Resend API" as email_api

[Client Browser] <--> [Flask App (app.py)] : HTTPS
[Flask App (app.py)] --> [SQLite (securevote.db)] : File I/O
[Flask App (app.py)] <--> [Face Utils (Facenet)] : Local Module
[Flask App (app.py)] --> email_api : REST API
@enduml
    """),

    # 9. System Architecture (Mermaid C4 / Flowchart)
    "9_System_Architecture.png": ("mermaid", """
flowchart TB
    UI[Frontend HTML/Jinja2]
    subgraph Backend [Flask Backend Framework]
        R[Router & Auth Controller]
        O[OTP Utils]
        F[Facial Recognition Engine]
    end
    DB[(SQLite Database)]
    API((Resend Mail API))

    UI <-->|HTTPS/REST| R
    R --> O
    O -->|API Call| API
    R --> F
    R <-->|Read/Write SQLite| DB
    """),

    # 10. Component Diagram (PlantUML)
    "10_Component_Diagram.png": ("plantuml", """
@startuml
package "Client Layer" {
  [Voter Web Interface] <<Frontend UI>>
  [Admin Dashboard] <<Frontend UI>>
}

package "Flask Application" {
  [Voter Controller] <<Route Handler>>
  [Admin Controller] <<Route Handler>>
  [Face Recognition Module] <<Service>>
  [OTP Module] <<Service>>
}

cloud "External" {
  [Resend Email API]
}

database "Persistence" {
  [SQLite DB]
  [Excel Source]
}

[Voter Web Interface] --> [Voter Controller] : HTTP
[Admin Dashboard] --> [Admin Controller] : HTTP
[Voter Controller] --> [Face Recognition Module]
[Voter Controller] --> [OTP Module]
[OTP Module] --> [Resend Email API]
[Voter Controller] --> [SQLite DB]
[Admin Controller] --> [SQLite DB]
[Admin Controller] --> [Excel Source]
@enduml
    """),

    # 11. Use Case Diagram (PlantUML)
    "11_Use_Case_Diagram.png": ("plantuml", """
@startuml
left to right direction
actor "Voter" as v
actor "Admin" as a
package "SecureVote System" {
  usecase "Register (OTP + Face)" as UC1
  usecase "Login (OTP + Face)" as UC2
  usecase "Cast Vote (OTP + Face)" as UC3
  usecase "Create Election" as UC4
  usecase "Manage Voters" as UC5
  usecase "View Results" as UC6
}
v --> UC1
v --> UC2
v --> UC3
a --> UC4
a --> UC5
a --> UC6
@enduml
    """)
}

diagram_dir = "diagrams"
os.makedirs(diagram_dir, exist_ok=True)
for filename, (type_, text) in diagrams.items():
    url = generate_kroki_url(type_, text)
    save_image(url, os.path.join(diagram_dir, filename))

print(f"All {len(diagrams)} diagrams generated successfully in {diagram_dir}/!")
