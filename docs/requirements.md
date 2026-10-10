# Apply Pilot Requirements

This document records requirements explicitly provided by the project owner. It will be updated as further requirements are discussed.

## 1. Overall Goal

Apply Pilot helps job seekers automatically fill in and submit job application information.

### 1.1. Usage and Deployment Scope

The first version is for the project owner's personal use only. After successful testing, the system may be deployed to a cloud server, with access restricted to the project owner.

Public availability is a future possibility. Before public availability, additional privacy management and system login functionality must be added. Their detailed requirements have not yet been defined.

### 1.2. Supported Job Sources

The initial version accepts LinkedIn job links and recruitment information pages on company websites. From either entry point, the system must retrieve the recruitment information, locate the company's application entry point, and continue to its application page. The intended LinkedIn entry flow retrieves publicly accessible job information without LinkedIn login, with the user login fallback described in Section 3.1.

The intended application destination scope includes all companies' external application websites, without a predefined restriction to specific companies or application platforms. Supporting applications across different company websites is a primary goal of the system.

LinkedIn on-platform applications are not supported. LinkedIn serves as the job information source and entry point to the company's external application website.

Support for Handshake, Indeed, and other job sources belongs to future development.

## 2. Applicant Information

Users must be able to save the information needed to apply for jobs in the system, including:

- Resumes.
- Experience.
- Skills.
- Personal information, such as a phone number.
- Other information required for job applications.

### 2.1. User Information Management Web Page

The system must provide a web page for managing applicant information.

### 2.2. Information Input

Users must be able to import PDF files, such as resumes. The system must extract applicant information from these files.

Users must also be able to enter information manually through a form or another convenient input method. The specific alternative input method has not yet been defined.

### 2.2.1. Confirmation, Conflicts, and Duplicates

Information extracted from uploaded documents must be confirmed by the user before it is saved.

When information from different sources is inconsistent, the user must decide which information to retain.

When information about to be entered conflicts with or duplicates information already in the applicant knowledge base, the system must notify the user. Entries describing the same experience must be merged, while different experiences must remain separate. Conflicts must be resolved by asking the user, and duplicate information must be consolidated into one entry with user approval.

### 2.3. Information Operations

Users must be able to create, view, update, and delete their applicant information.

Every addition, modification, or deletion of user information requires the user's approval. Searching and viewing information do not require approval. This also applies to changes proposed during application tasks and information consolidation.

When the user clicks Save, the system must check whether the information is missing from the stored data or conflicts with existing information. In either case, it must explain that the information is new or conflicting and ask the user to confirm saving it. This confirmation behavior may be revised after testing if it proves too cumbersome.

### 2.4. Information Storage Scope

The applicant knowledge base must save objective factual information related to job applications, rather than subjective answers written by the user. User account identifiers and passwords must not be saved, and verification codes must not be recorded. Other information within the defined storage scope must be saved with user approval.

The detailed personal information fields will be defined during system design.

Login email addresses must not be saved as account information. Email addresses required as applicant information in application forms may be saved. The system must support multiple applicant email addresses with distinct purposes, such as a contact email and a response email. If no separate purpose is specified, the same email address is used for those purposes.

## 3. Application Entry and Form Completion

The user provides a job application entry point, such as a company website or a LinkedIn job listing. The system finds the corresponding application page and fills in the user's information.

During form completion, the agent may enter only information it is certain about. When information is uncertain, the system must ask the user. Information approved for saving must be synchronized to the stored applicant information in real time during form completion. The user may instead choose to use supplied information only for the current application without updating their stored applicant information.

### 3.1. Starting an Application with a Job URL

After the user has prepared their applicant information and resumes, they can start an application by sending a request to apply for a job together with its URL.

Example request: "Help me apply for https://www.linkedin.com/jobs/view/4462540652/".

For this LinkedIn entry flow, the requested behavior is to retrieve the job information and locate the company's application page without requiring LinkedIn login. The URL above is a user-provided example; its page contents and accessibility have not been verified as part of this requirements document.

If the website cannot be accessed while retrieving job posting information, the system may ask the user to log in personally so that an access credential can be obtained. The system must not request or obtain the user's password from the user. The specific type of access credential and how it is obtained have not yet been defined.

### 3.2. Application Workflow

1. Receive the user's application request and job URL.
2. Retrieve the job posting information.
3. Locate and open the company's corresponding application page.
4. Select the appropriate user-provided resume based on its filename and the job information.
5. Fill in the application using confirmed applicant information. Ask the user about uncertain information, then let the user choose whether to update their stored applicant information in real time or use the supplied information only for the current application. When highly private information is required, pause for the user to enter it personally.
   For each page, show the user what has been filled in and obtain confirmation before proceeding to the next page.
6. Return all completed application information for user review on a new web page or through a PDF export, according to the user's choice.
7. Submit the application after the user's review and confirmation.
8. As soon as the application is sent, begin saving the company, job, associated recruitment information, and submitted application information in the application management area. Update the result when confirmation is available; otherwise, mark it as pending confirmation.

### 3.3. Determining and Preparing Confirmed Information

The system must find relevant information in the stored applicant data and adapt it to the fields required by the application form. Confirmed information is not limited to values stored in exactly the same format as the form expects.

- **Direct matching:** If the stored gender is male and the form asks for gender, the system can use the stored value.
- **Combining and splitting:** The system must be able to combine or split stored information to match the form's fields when the result is certain. For example, if the stored first name is `hong` and last name is `li`, the system can combine them in a single field requesting both names, using the format required by the form.
- **Calculation:** The system must be able to calculate a requested value from stored information. Age calculations must use a complete date of birth, including year, month, and day, to determine accurate age. If the stored date of birth lacks any of these components, the system must ask the user for the missing information rather than estimate age from the birth year alone.

### 3.4. Missing Information and Human-in-the-Loop Completion

When the stored data is insufficient to determine a requested value, the system must ask the user to provide the missing information through a human-in-the-loop step.

For example, if the application asks for the user's specific city of residence but the stored data contains only their state of residence, the system must ask the user for the city.

The information supplied by the user must be used to continue filling in the application. If the user approves updating their profile, the information must be synchronized to the stored applicant information in real time. If the user chooses not to update their profile, the information must be used only for the current application. The requirement to retain submitted information in that application's historical record still applies.

Saved changes must continue to follow the information change prompts and confirmation rules. Further details of this information management module will be discussed during its design.

### 3.5. Non-Factual Questions

The AI must not draft answers to non-factual application questions. The system must ask the user to write these answers personally.

Subjective answers must not be saved in the applicant knowledge base, but must be retained as part of the complete historical application record. A future version may use historical responses to propose recommended answers that the user can accept or reject; this is not part of the current version. How historical responses would be used to generate recommendations has not yet been defined.

### 3.6. Failures and Submission Results

If a job posting is no longer available, an application entry point cannot be found, or another problem occurs, the system must inform the user and ask how to proceed, such as stopping the application or providing additional information.

After submission, if the website returns a page requiring further information or user actions, the system must direct the user to that page to complete those steps.

If the returned page only indicates successful submission, the system must display an application success message and update the application management area. A returned success page is the expected success signal in this workflow.

If the submission result is uncertain, the system must ask the user whether an application confirmation email was received. If the user confirms receipt, the application must be marked successful. If no confirmation notification has been received, the result must be marked pending confirmation rather than being marked failed solely because no email arrived. The system must inform the user that no confirmation email was reported and allow the user to decide whether to apply again.

The submitted application must be saved even if the user cancels the task or closes the page after the application has been sent. The full set of submission states and their meanings will be defined during system design.

### 3.7. Task Validation and Duplicate Application Checks: Deferred

For a later version intended for broader use, the system must validate whether the user's application task is feasible before retrieving job information, and search application records to determine whether the job has already been applied for.

These checks are recorded for future development and are not required in the initial version. The initial version assumes that the user does not provide duplicate application requests. The detailed feasibility criteria and handling of previously applied-for jobs have not yet been defined.

## 4. Human-in-the-Loop Steps

When the application process requires highly private information, such as credentials for account creation, the user must enter that information personally. The workflow must include a human-in-the-loop verification step for these situations.

The user must also review the application before submission.

### 4.1. User Login During Browser Tool Execution

When an agent uses a browser simulation tool and encounters a login step requiring a password, it must pause the automated workflow and ask the user to log in personally. The system must not ask the user to provide their password to the agent or system.

After the user completes login and an access credential becomes available, the agent must use the authenticated access to continue visiting the website and complete the remaining task steps, subject to the other human-in-the-loop requirements in this document.

The user login step is the means of obtaining authenticated access in this workflow. The specific credential representation and technical mechanism have not yet been defined.

Login access credentials must be used only for a single application task and must not be retained for reuse in subsequent tasks. Some application websites may not require registration or login.

The user should be able to see the browser and the operations being performed, similar to the browser displayed beside this conversation. When user input is required, automation must pause, allow the user to operate the page, and continue after the user has completed the required input.

After completing a manual operation, the user must be able to resume the task by clicking Continue or sending a message indicating that the operation is complete and work should continue.

Verification challenges, including CAPTCHA and other verification steps, must be handled by the user. The system must not record the user's verification codes.

### 4.2. Application Review and Submission Approval

In the initial version, the system must show what has been filled in on each application page and require the user's confirmation before proceeding to the next page. Autonomous page progression may be considered in a future version after the program has demonstrated reliable operation with few errors.

When declarations or agreement to terms are encountered, the user must personally click to confirm them.

After all application information has been filled in, the system must return all filled-in information for the user to review.

The user must be able to choose between viewing this information on a new web page and exporting it as a PDF for review.

The system may submit the application only after the user has checked the information and explicitly agreed to submission.

If changes are required during review, the user must have two options:

- Provide the information to be changed to the system so it can update the application.
- Access the application website's page and modify the information personally.

Submission still requires the user's approval after review.

When the user modifies the application directly on the website, the system should detect the changes where possible. The supported detection and synchronization behavior for the review information and final application record will be determined according to the browser tool's capabilities and testing results.

### 4.3. Conversation Interface, User Input, and Progress

The project must provide a GPT-like conversation interface. During task execution, it must display real-time progress updates and present forms or input boxes for the user to supply required information.

Closing the system page stops the application task. When the user reopens the page, the previous task must be cancelled and cannot be resumed. This replaces the earlier expectation of resuming a task after closing the page. User-initiated cancellation must also stop application execution.

After cancellation, all data displayed for that task must disappear from the interface. Changes to applicant information that were already approved and saved during form completion must remain saved; cancellation must not roll them back. Removal of displayed task data does not define deletion of underlying stored task data.

The initial version must execute only one application task at a time. A future version may support asynchronous execution with multiple application agents working on different applications concurrently.

## 5. Application Management

As soon as an application is sent, the system must begin saving its record in a dedicated area for managing job applications, without waiting for confirmation of success. If no confirmation notification has been received, the record must be marked pending confirmation. When success is confirmed, the result must be updated. This area stores information about the job that was applied for.

### 5.1. Job Posting Information

When applying for a job, the system must also save its recruitment information, including qualifications, requirements, and salary information provided in the job posting.

The detailed recruitment information fields and storage format will be discussed during system design.

### 5.2. Application Records: Initial Scope

The initial scope includes saving application records and allowing users to find the following information together in the application management area:

- Company name.
- Application date.
- The job applied for.
- The associated job posting information.
- The application information that was submitted.

The saved job posting information must be available for the user to review again when preparing for an interview.

Additional historical application record fields may be defined or added during subsequent design.

Historical application records must retain all submitted application information, including subjective answers written by the user. This allows the user to review exactly what information they used to apply to a company when preparing for an interview. Subjective answers are retained in the application history, not in the applicant knowledge base. Account identifiers, passwords, and verification codes must not be retained, in accordance with the storage exclusions above.

### 5.3. Application Management: Future Development

The application management module will be expanded after the basic functionality has been completed. The following requirements belong to that later development scope:

- Update the status of a specific application when the user reports an outcome or progress for a company and position, such as acceptance, rejection, or entering the interview stage.
- Support requests to retrieve job posting information for positions whose interviews the user needs to prepare for.

The complete set of application statuses and further management features have not yet been defined.

## 6. Initial Development Scope: Application Documents

Application document management must cover user-provided files to be uploaded during applications, including resumes, cover letters, transcripts, and certificates. Applicant information management handles the data entered into form fields; document management handles the uploaded attachments. Facts extracted from a document and confirmed by the user belong to applicant information management, while the original file belongs to document management.

The initial development scope does not require agents to generate resumes from personal information.

Users provide multiple resumes themselves. The AI selects the appropriate user-provided resume according to the application context.

The resume selection rules below apply specifically to resumes. Selection and usage rules for other document types will be defined during detailed module design.

### 6.1. Resume Selection by Filename and Job Information

When users upload multiple resumes, the system must use their filenames and the information about the job being applied for to select the most suitable resume.

For example, a user may provide `name_ai_resume.pdf` for AI positions and `name_software_engineer_resume.pdf` for software engineering positions. The system must determine which resume corresponds best to the current job based on the job information and the intended role indicated by each filename.

### 6.2. Resume Selection Failure

When the system cannot select an appropriate resume, it must ask the user to choose and confirm a resume or add a new resume.

### 6.3. Document Modification, Renaming, and Deletion

Users must be able to upload, modify, rename, and delete application documents, subject to user approval for changes to user information.

- **Soft deletion:** Display the document as deleted to the user and mark it as unavailable for future use. Retain the stored file so historical application records can still access it.
- **Permanent deletion:** Inform the user which application records will be affected and obtain confirmation before permanently deleting the document. Mark the corresponding file in affected records as deleted.
- **Renaming:** Update the document's name in associated application records.

When a document is modified, the old version must be retained for historical application records so that the user can review the file that was actually submitted. The previously defined permanent deletion behavior still applies when the user chooses to permanently delete a retained document.

## 7. Future Fully Automatic Mode

After the basic functionality and the application management expansion have been completed, a fully automatic mode may be considered. This potential mode would search for job postings, match suitable positions, and automatically apply for them.

This is a future idea for consideration, not a requirement for the initial version. Its detailed behavior and approval rules have not yet been defined.

## 8. Browser Automation Tooling

The system must use an open-source MCP server or open-source browser automation tool to provide agents with the browser interaction capabilities required by the application workflow, including accessing pages and filling in application forms.

The integration must support the human-in-the-loop login, input, review, and submission requirements defined in this document.

The specific tool and integration approach have not yet been selected. This requirement does not mandate MCP as the only integration method.

## 9. Future User Information Encryption

A future version must encrypt all stored user information and decrypt it when needed for use. System operators must not be able to view users' information in plaintext; direct inspection of databases or stored documents must expose only encrypted contents.

The key management and access mechanisms needed to meet this requirement have not yet been defined.

## 10. Acceptance Criteria

Detailed acceptance criteria are deferred. This is a practice project, and requirements may be adjusted during development.
