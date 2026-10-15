# Technology Stack Decisions

## 1. Status

This document records technology choices confirmed by the project owner. Implementation details that have been deferred are listed separately. The project remains in design; the components below have not yet been implemented.

## 2. Confirmed Choices

| Area | Choice | Scope |
| --- | --- | --- |
| Frontend framework | React | Separate frontend application. |
| Frontend language | TypeScript | Frontend application code. |
| Styling | Bootstrap | Frontend styling framework. |
| Tooling runtime | Node.js | Frontend development and build tooling. |
| Build tool | Vite | Frontend development server and builds. |
| Frontend package manager | pnpm | Frontend dependency management. |
| Frontend port | 5173 | Local development server. |
| Backend | Python and FastAPI | APIs and backend business modules. |
| Backend port | 8000 | Backend application server. |
| Python management | uv | Python versions, environments, and dependencies. |
| Source version control | Git | Code and documentation history. |
| Relational database | PostgreSQL in Docker | Structured information and relational application data. |
| File storage | Local directory | Application documents and retained versions; cloud storage later. |
| Agent ecosystem | Deep Agents, LangChain, and LangGraph | Specific agent roles and integration details later. |
| Agent observability | LangSmith | Monitoring, tracing, and evaluation; trace contents to be designed. |
| Python testing | pytest | Backend and agent-related automated tests. |
| Browser automation | Playwright MCP | Initially a local visible browser; frontend integration later. |
| Supplemental retrieval | RAG backed by OpenSearch | Supplemental facts and user-confirmed non-fixed preferences. |
| Embedding model | OpenAI `text-embedding-3-small` | Initial lower-cost choice; reassess if retrieval quality is insufficient. |
| Redis | Applicant drafts and login sessions | Seven-day JSON profile drafts; one active device login per user. Logout or 10 hours of inactivity invalidates the session; user operations/access refresh it. |
| CI/CD | Jenkins | Pipeline checks, triggers, hosting, and deployment details remain to be designed. |

## 3. Database Access Boundary

Applicant information management encapsulates its database connection and access through a driver and exposes business operations. Agent tools call those operations rather than accessing the database directly.

The module continues to enforce validation, conflict handling, and user approval for additions, modifications, and deletions. The database driver, any ORM, migration tooling, and connection lifecycle have not yet been selected. The frontend accesses backend APIs rather than connecting directly to PostgreSQL.

### 3.1. Draft Storage

The system must allow incomplete applicant information to be saved as a JSON draft in Redis for seven days. Registration generates a user ID and creates a PostgreSQL `user` record containing the ID, username, and password hash. Associate drafts with this ID and retrieve an unexpired draft by the authenticated user's ID after restarting or reopening the system. Do not create the applicant profile in PostgreSQL while it is incomplete. When the information is complete and approved for formal saving, use the same user ID for PostgreSQL storage. An authentication account is separate from a complete applicant profile; account creation does not require creating an incomplete profile.

Unconfirmed profile edits may also be saved in Redis, including incorrectly formatted values. Apply full field validation before SQL saving. After successful SQL saving, delete only the corresponding SQL profile draft version; SQL failure must retain it and return a reason for correction. RAG saving is a separate operation with its own result and retained pending contents on failure; SQL draft cleanup must not remove them. Formal profile data is authoritative, and conflicting proposed changes require user resolution. Whether editing restarts the seven-day period, Redis persistence configuration, and RAG retry details remain to be designed. This draft is applicant information, not a resumable browser application task.

## 4. Structured Information and RAG

Common structured information, such as names and standard applicant fields, belongs in PostgreSQL. These fields do not need to be duplicated in the supplemental collection merely for RAG.

The profile page shows the structured form above a large free-text box for any supplemental information the user wishes to provide. The form and supplemental box use separate save operations: SQL for structured fields, and RAG for approved supplemental information. They do not form a combined save transaction.

Some application questions require uncommon facts not represented by the common SQL fields. When the user supplies such information and chooses to save it, its description or summary is intended to be stored for retrieval through OpenSearch. OpenAI `text-embedding-3-small` generates the embeddings.

This supplemental information may change over time. Update, conflict, and stale-information handling will be designed within the information module. Saving or summarizing facts requires user approval and must preserve the user's meaning.

User-confirmed non-fixed job preferences, including desired compensation, must also be stored in this RAG collection. These preferences are distinct from subjective narrative answers written for a particular application. Their updates follow the same user choice and confirmation rules.

The intended retrieval flow is:

1. Look for sufficient confirmed information in structured applicant data.
2. If insufficient, retrieve relevant supplemental facts or user-confirmed preferences through RAG.
3. If information remains missing, conflicting, or uncertain, ask the user.
4. Let the user choose an approved persistent update or one-time use.

Subjective narrative application answers remain excluded from the reusable applicant knowledge base, including its RAG collection; this exclusion does not apply to user-confirmed job preferences. Submitted subjective answers still belong in historical application records. A similar retrieved passage is not automatically confirmed current information.

OpenSearch provides storage and retrieval, while the embedding model converts text to vectors. Neither choice selects the agent's generative model.

## 5. Deferred Decisions

| Decision | Current Position |
| --- | --- |
| Generative model and provider | Not selected. |
| Agent roles, tools, and orchestration | Selected ecosystem; details later. |
| Independent agent SDK or service | Possible future separation; SDK and inference interface details remain open. |
| Real-time communication | Decide when designing the relevant workflow. |
| Frontend browser display and takeover | Start locally; frontend integration later. |
| Database driver, ORM, and migrations | Not selected. |
| OpenSearch deployment and persistence | Not selected. |
| Redis draft lifecycle | Seven-day drafts permit incomplete or incorrectly formatted values; validate before SQL saving. Delete after SQL success, retain on SQL failure. Expiration refresh, restart persistence, and concurrent edits remain open. |
| System authentication implementation | PostgreSQL `user` accounts and Redis sessions; a successful new login replaces the old device's session. Case-sensitive unique usernames; passwords 10-30 characters inclusive with letters, digits, and special characters. ID/schema details, character sets, session transport, and hashing remain open. |
| Exact runtime and dependency versions | Pin during project initialization. |
| Configuration and secrets handling | Design before implementing dependent components. |
| LangSmith trace contents | Define permitted data and enforce storage exclusions. |
| Frontend testing tools | Not selected. |
| Jenkins pipeline | Platform confirmed. Hosting, checks, triggers, deployment target, and release approval behavior remain open. |

These decisions do not add new business features. Detailed module specifications belong under [Detailed Design](../detailed-design/README.md).

## 6. CI/CD Planning

The project must use Jenkins for CI/CD as part of its development workflow. The platform is confirmed; no pipeline has been implemented yet.

- **Continuous integration:** Proposed coverage includes automated validation, tests, and builds. Exact checks and triggering events will be agreed upon when the pipeline is designed.
- **Continuous delivery or deployment:** The deployment target, timing, and whether deployment requires manual approval remain undecided. Cloud deployment remains a later project stage.
- **Platform:** Jenkins. Its hosting and integration with the GitHub repository will be designed later.

The earlier GitHub Actions suggestion is superseded by the project owner's selection of Jenkins.
