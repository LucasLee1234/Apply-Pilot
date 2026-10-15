# Apply Pilot Documentation

This directory contains all project documentation and written work outside application code. All documents are written in English.

## Documentation Index

| Area | Document | Purpose |
| --- | --- | --- |
| Requirements | [Requirements](requirements/requirements.md) | Confirmed requirements and deferred scope. |
| Overall design | [Overall Analysis](design/overall-analysis.md) | Six modules, boundaries, and collaboration diagram. |
| Technology decisions | [Technology Stack](design/technology-stack.md) | Confirmed choices and unresolved decisions. |
| Shared response contract | [Response Format](design/response-format.md) | Common JSON result envelope for modules, APIs, and agent tools. |
| Detailed design | [Detailed Design Index](detailed-design/README.md) | Module design status and specifications. |
| Applicant information inputs | [Input Fields](detailed-design/personal-information/inputs.md) | Field inventory and validation questions for review. |
| Applicant save confirmation | [Save Confirmation Flow](detailed-design/personal-information/save-confirmation.md) | Pending changes, user approval, saving, cancellation, and failure. |
| Supplemental information | [Independent RAG Saving](detailed-design/personal-information/supplemental-information.md) | Free-text input, separate save results, and failure retention. |
| Registration and login | [Initial Scope](detailed-design/authentication/README.md) | Basic username/password accounts and draft identity association. |

## Organization

```text
docs/
├── README.md
├── requirements/
│   └── requirements.md
├── design/
│   ├── overall-analysis.md
│   ├── technology-stack.md
│   └── response-format.md
└── detailed-design/
    ├── README.md
    ├── personal-information/
    │   ├── inputs.md
    │   ├── save-confirmation.md
    │   └── supplemental-information.md
    └── authentication/
        └── README.md
```

Keep requirements in `requirements/`, cross-module design and technology decisions in `design/`, and module specifications in `detailed-design/`. Create additional module directories as their specifications are written.
