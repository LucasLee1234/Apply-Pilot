# Detailed Module Design

Each of the six core business modules and the supporting registration and login module has its own documentation subdirectory. Directory names below are documentation conventions, not implementation package requirements.

| Business Module | Directory | Current Status |
| --- | --- | --- |
| Applicant Information Management | `personal-information/` | [Input fields](personal-information/inputs.md), [SQL save confirmation](personal-information/save-confirmation.md), and [independent RAG saving](personal-information/supplemental-information.md) available; full design incomplete. |
| Application Document Management | `application-documents/` | Not yet written. |
| Job Information and Application Entry Identification | `job-information/` | Not yet written. |
| Application Execution and Human Collaboration | `application-execution/` | Not yet written. |
| Application Review and Submission | `review-and-submission/` | Not yet written. |
| Application Record Management | `application-records/` | Not yet written. |
| Registration and Login (supporting module) | `authentication/` | [Initial scope](authentication/README.md) recorded; detailed design incomplete. |

Only directories with existing specifications have been created. Create the others when their specifications are written. Documents may cover inputs, outputs, processing flows, data structures, interfaces, and exception handling as each module is discussed.

Project-wide context: [Requirements](../requirements/requirements.md), [Overall Analysis](../design/overall-analysis.md), and [Technology Stack](../design/technology-stack.md).
