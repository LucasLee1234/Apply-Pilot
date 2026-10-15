# Supplemental Information: Independent RAG Saving

## 1. Input and Boundary

The applicant information page displays structured fields and, below them, a large free-text box for any additional information the user wishes to provide.

The structured form saves to SQL. The supplemental box saves independently through the RAG flow, using OpenSearch and the selected embedding model. There is no combined SQL/RAG save transaction, and each operation has its own result using the [Shared Response Format](../../design/response-format.md).

Supplemental information remains subject to the agreed storage rules: reusable facts and user-confirmed preferences are allowed; job-site credentials and verification codes must not be retained. Subjective narrative application answers belong in historical application records rather than this reusable collection.

## 2. Save and Failure Handling

- Obtain user approval for supplemental additions, changes, and summaries under the existing confirmation rules.
- Preserve the user's meaning when preparing descriptions or summaries for retrieval.
- On a successful RAG save, report that operation's success independently of SQL.
- On embedding or OpenSearch save failure, return that operation's failure and retain the unsaved supplemental contents separately for retry.
- SQL success must not delete pending supplemental contents. RAG failure must not change a successful SQL result into failure, and SQL failure must not determine the result of an independent RAG save.
- Apply authenticated ownership checks, confirmation binding, version checks, and repeat-execution protection to approved RAG changes as well as SQL changes.

## 3. Pending Details

Pending supplemental content storage, retention duration, retry invocation and cleanup, exact API payloads, error codes, and retrieval update/staleness rules remain to be designed. These are separate from the existing seven-day SQL profile draft policy unless a later decision explicitly unifies their retention.
