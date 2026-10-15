# Apply Pilot Documentation

This directory contains all project documentation and written work outside application code. All documents are written in English.

## Documentation Index

| Area | Document | Purpose |
| --- | --- | --- |
| Requirements | [Requirements](requirements/requirements.md) | Confirmed requirements and deferred scope. |
| Overall design | [Overall Analysis](design/overall-analysis.md) | Six modules, boundaries, and collaboration diagram. |
| Technology decisions | [Technology Stack](design/technology-stack.md) | Confirmed choices and unresolved decisions. |
| Detailed design | [Detailed Design Index](detailed-design/README.md) | Module design status and specifications. |
| Applicant information inputs | [Input Fields](detailed-design/personal-information/inputs.md) | Field inventory and validation questions for review. |

## Organization

```text
docs/
├── README.md
├── requirements/
│   └── requirements.md
├── design/
│   ├── overall-analysis.md
│   └── technology-stack.md
└── detailed-design/
    ├── README.md
    └── personal-information/
        └── inputs.md
```

Keep requirements in `requirements/`, cross-module design and technology decisions in `design/`, and module specifications in `detailed-design/`. Create additional module directories as their specifications are written.
