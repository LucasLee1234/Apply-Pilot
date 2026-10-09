# Apply Pilot Requirements

This document records requirements explicitly provided by the project owner. It will be updated as further requirements are discussed.

## 1. Overall Goal

Apply Pilot helps job seekers automatically fill in and submit job application information.

### 1.1. Usage and Deployment Scope

The first version is for the project owner's personal use only. After successful testing, the system may be deployed to a cloud server, with access restricted to the project owner.

Public availability is a future possibility. Before public availability, additional privacy management and system login functionality must be added. Their detailed requirements have not yet been defined.

### 1.2. Supported Job Sources

LinkedIn is the only job information source in the initial version. The intended entry flow retrieves publicly accessible job information without LinkedIn login, with the user login fallback described in Section 3.1. The application workflow continues to the company's corresponding application page.

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

When information about to be entered conflicts with or duplicates information already in the applicant knowledge base, the system must notify the user. The user must decide which entry to keep, and only one entry must be retained for that conflicting or duplicate information.

### 2.3. Information Operations

Users must be able to create, view, update, and delete their applicant information.

### 2.4. Information Storage Scope

The system must save all information related to and required for job applications. The detailed list of information fields has not yet been defined.

## 3. Application Entry and Form Completion

The user provides a job application entry point, such as a company website or a LinkedIn job listing. The system finds the corresponding application page and fills in the user's information.

During form completion, the agent may enter only information it is certain about. When information is uncertain, the system must ask the user. The latest information obtained from the user must then be synchronized to the stored applicant information.

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
5. Fill in the application using confirmed applicant information. Ask the user about uncertain information and synchronize their answers to the stored applicant information. When highly private information is required, pause for the user to enter it personally.
6. Return all completed application information for user review on a new web page or through a PDF export, according to the user's choice.
7. Submit the application after the user's review and confirmation.
8. After successful submission, update the application record with the company, job, associated recruitment information, and the application information that was submitted.

### 3.3. Determining and Preparing Confirmed Information

The system must find relevant information in the stored applicant data and adapt it to the fields required by the application form. Confirmed information is not limited to values stored in exactly the same format as the form expects.

- **Direct matching:** If the stored gender is male and the form asks for gender, the system can use the stored value.
- **Combining and splitting:** The system must be able to combine or split stored information to match the form's fields when the result is certain. For example, if the stored first name is `hong` and last name is `li`, the system can combine them in a single field requesting both names, using the format required by the form.
- **Calculation:** The system must be able to calculate a requested value from stored information. The user-provided example is calculating age from a stored birth year of 2000. The required age precision and treatment of an unknown birthday have not yet been defined; a birth year alone does not determine exact current age.

### 3.4. Missing Information and Human-in-the-Loop Completion

When the stored data is insufficient to determine a requested value, the system must ask the user to provide the missing information through a human-in-the-loop step.

For example, if the application asks for the user's specific city of residence but the stored data contains only their state of residence, the system must ask the user for the city.

The information supplied by the user must be used to continue filling in the application and synchronized to the stored applicant information, as described above.

### 3.5. Non-Factual Questions

The AI must not draft answers to non-factual application questions. The system must ask the user to write these answers personally.

### 3.6. Failures and Submission Results

If a job posting is no longer available, an application entry point cannot be found, or another problem occurs, the system must inform the user and ask how to proceed, such as stopping the application or providing additional information.

After submission, if the website returns a page requiring further information or user actions, the system must direct the user to that page to complete those steps.

If the returned page only indicates successful submission, the system must display an application success message and update the application management area. A returned success page is the expected success signal in this workflow.

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

### 4.2. Application Review and Submission Approval

After all application information has been filled in, the system must return all filled-in information for the user to review.

The user must be able to choose between viewing this information on a new web page and exporting it as a PDF for review.

The system may submit the application only after the user has checked the information and explicitly agreed to submission.

The project owner noted that many application websites provide a final review of the completed information. How to modify application information during review will be discussed later and has not yet been defined.

### 4.3. Conversation Interface, User Input, and Progress

The project must provide a GPT-like conversation interface. During task execution, it must display real-time progress updates and present forms or input boxes for the user to supply required information.

When the user closes the page or cancels an application task, the application task must pause. The mechanism for resuming a paused task has not yet been defined.

## 5. Application Management

After a successful submission, the system must update a dedicated area for managing job applications. This area stores information about the job that was applied for.

### 5.1. Job Posting Information

When applying for a job, the system must also save its recruitment information, including qualifications, requirements, and salary information provided in the job posting.

### 5.2. Application Records: Initial Scope

The initial scope includes saving application records and allowing users to find the following information together in the application management area:

- Company name.
- The job applied for.
- The associated job posting information.
- The application information that was submitted.

The saved job posting information must be available for the user to review again when preparing for an interview.

### 5.3. Application Management: Future Development

The application management module will be expanded after the basic functionality has been completed. The following requirements belong to that later development scope:

- Update the status of a specific application when the user reports an outcome or progress for a company and position, such as acceptance, rejection, or entering the interview stage.
- Support requests to retrieve job posting information for positions whose interviews the user needs to prepare for.

The complete set of application statuses and further management features have not yet been defined.

## 6. Initial Development Scope: Resumes

The initial development scope does not require agents to generate resumes from personal information.

Users provide multiple resumes themselves. The AI selects the appropriate user-provided resume according to the application context.

### 6.1. Resume Selection by Filename and Job Information

When users upload multiple resumes, the system must use their filenames and the information about the job being applied for to select the most suitable resume.

For example, a user may provide `name_ai_resume.pdf` for AI positions and `name_software_engineer_resume.pdf` for software engineering positions. The system must determine which resume corresponds best to the current job based on the job information and the intended role indicated by each filename.

### 6.2. Resume Selection Failure

When the system cannot select an appropriate resume, it must ask the user to choose and confirm a resume or add a new resume.

## 7. Future Fully Automatic Mode

After the basic functionality and the application management expansion have been completed, a fully automatic mode may be considered. This potential mode would search for job postings, match suitable positions, and automatically apply for them.

This is a future idea for consideration, not a requirement for the initial version. Its detailed behavior and approval rules have not yet been defined.
