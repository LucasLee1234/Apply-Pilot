# Apply Pilot

Apply Pilot is a personal job application assistant designed to help fill in and submit applications on company career websites, using applicant information and application documents supplied by the user.

## Project Status

Requirements analysis and overall business module design have been completed. Technology selection and detailed module design are in progress. Application code has not yet been implemented. The capabilities described below are planned requirements.

## Planned Technology Stack

- Frontend: TypeScript and React.
- Backend: Python and FastAPI.
- Automation: a multi-agent system with browser tools and human-in-the-loop interactions.
- Architecture: separate frontend and backend.

## Initial Scope

- Provide basic Apply Pilot registration and login using a username and password, with user-linked applicant drafts retained in Redis for seven days.
- Manage applicant information through PDF resume extraction and manual entry, with user confirmation before saving extracted information.
- Start an application from a user-provided LinkedIn job URL or company recruitment page and locate the company's external application page. LinkedIn on-platform applications are excluded.
- Manage application attachments, including resumes, cover letters, transcripts, and certificates, with version retention and deletion controls.
- Select a user-uploaded resume using its filename and the job information.
- Fill forms using confirmed information, including supported combinations, splits, and calculations of stored data.
- Ask the user for missing information, conflicting data decisions, and answers to non-factual questions. The AI must not draft non-factual answers.
- Pause for the user to log in personally when needed, then continue with authenticated access without requesting the user's password.
- Show real-time progress and request user input through a conversation interface, forms, or input boxes.
- Present all completed information on a review page or as a PDF export. Submit only after explicit user approval.
- Save the company, position, recruitment information, and submitted application information in application records.

The initial version is for the project owner's use only. Cloud deployment may follow successful testing, with access restricted to the owner.

## Future Scope

Future work includes additional job sources such as Handshake and Indeed, expanded application record management, and task validation and duplicate application checks for broader use. Public availability would require additional privacy and public-access management beyond the initial basic login functionality.

A fully automatic job search, matching, and application mode may be considered after the basic functionality and application management expansion are complete.

## Documentation

- [Requirements](docs/requirements/requirements.md): confirmed requirements and deferred scope.
- [Overall Analysis](docs/design/overall-analysis.md): business modules and collaboration.
- [Technology Stack](docs/design/technology-stack.md): confirmed choices and pending decisions.
- [Detailed Design](docs/detailed-design/README.md): module specifications and status.
- [Documentation Guide](docs/README.md): purpose of the documentation directory.

All project documentation is written in English and kept in `docs/`.

## Repository Layout

```text
Apply-Pilot/
├── README.md
└── docs/
    ├── README.md
    ├── requirements/
    ├── design/
    └── detailed-design/
```
