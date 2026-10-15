# Applicant Information Management: Input Fields

## 1. Scope and Status

This draft organizes the input fields provided by the project owner for applicant information management. It is a business-level field inventory for review, not a finalized API contract or database schema. Operation-specific outputs and complete processing flows remain to be designed; their envelope must follow the [Shared Response Format](../../design/response-format.md).

For a complete profile, all input fields are required by default except Preferred Name, Phone Extension, Previous Employers, To, Minor, Anticipated Graduation Date, and Social Network URLs. Minor may be omitted or set to None to indicate no minor. Type of Degree Being Pursued is an optional application question using the relevant education entry, not a duplicate input. GPA is required for each provided education entry. Education Status is required; Graduation Date is required only for a graduated entry. This replaces the earlier optional Already Graduated field. Incomplete information may be retained as a Redis draft under Section 12. These rules do not define required fields on third-party application websites.

Work Experience, Education, and Skills may each contain zero entries. An empty list represents no entries; the user does not need to create a placeholder entry. Required field rules apply when an entry is provided. Suggested data categories describe the information; they do not finalize UI controls or technical storage types.

The initial version supports United States addresses and telephone details. Country-dependent labels and validation must be taken into account, but other countries are outside the initial supported scope.

## 2. Identity and Address

| Field | Information Type | Description and Rules | Optionality |
| --- | --- | --- | --- |
| Country | Country selection | Country used to determine address labels and country-specific handling. Only the United States is supported initially. | Required. |
| First Name | Text | Applicant's first name. | Required. |
| Last Name | Text | Applicant's last name. | Required. |
| Preferred Name | Text | Name the applicant prefers to use. | May be empty. |
| Address | Text | Applicant's address. Address labels must depend on the selected country. Initial support is for the United States. | Required. |
| City | Text | City component of the applicant's address. | Required. |
| State | Country-dependent selection | Options depend on Country. Initially Country supports only US, with United States states as the options. Other countries are deferred. | Required. |
| Postal Code | Postal code value | United States ZIP Code, validated under Section 11. | Required. |
| Date of Birth | Date value | Complete birth date with year, month, and day. Used to calculate accurate age when required. Missing components must be requested rather than estimated. | Required. |

Age is calculated from the complete date of birth when needed. It is not a separately maintained input field.

## 3. Contact Information

| Field | Information Type | Description and Rules | Optionality |
| --- | --- | --- | --- |
| Default Email | Single email value | Exactly one applicant email address in the initial version. Validated under Section 11. Mailbox existence or ownership verification has not been specified. | Required. |
| Phone Device Type | Selection | Mobile, Home, Landline, Other. | Required. |
| Country Phone Code | Selection | A country-dependent calling-code list is required. Only the United States calling code is supported in the initial version. | Required. |
| Phone Number | Telephone value | United States number, validated under Section 11. | Required. |
| Phone Extension | Extension value | Extension associated with the telephone number. | May be empty. |

Multiple applicant email addresses and purpose-specific routing are deferred. The initial version uses Default Email. Login email addresses must not be retained as account information.

## 4. Employer History and Company Matching

The system must be able to represent the companies the applicant has worked for. This supports application questions asking whether the applicant has previously worked for the hiring company.

| Item | Description | Status |
| --- | --- | --- |
| Previous Employers | An optional list of company-name strings; may be omitted. | Initially a list of strings. |
| Company Name Matching | An abbreviated company name and its full name should be recognizable as the same company. | Matching and user confirmation rules require further design. |
| Relationship to Work Experience | Employer history overlaps with the companies in work experience entries. | Whether it is derived from those entries or managed separately has not been decided. |

No company alias algorithm or automatic conflict-resolution rule is selected in this draft.

## 5. Work Experience

Work experience is a list supporting zero or more entries. Each provided entry must support the following fields.

| Field per Entry | Information Type | Description and Rules | Optionality |
| --- | --- | --- | --- |
| Job Title | Text | Title of the role held. | Required. |
| Company | Company name | Employer associated with the role. Company abbreviation and full-name matching require further design. | Required. |
| From | Month and year | Start of the employment period. No day component. | Required. |
| To | Month and year | End of the employment period. No day component. Optional, including when Currently Employed is selected. | May be empty. |
| Currently Employed | Selection | Indicates whether the applicant is still employed in this role. | Required. |
| Role Description | Text | Description of the applicant's work in this role. | Required. |

## 6. Education

Education is a list supporting zero or more entries. Current study and graduation information belongs to its corresponding education entry rather than a separate profile section. Each provided entry must support the following fields.

| Field per Entry | Information Type | Description and Rules | Optionality |
| --- | --- | --- | --- |
| School or University | Institution value | School or university attended. | Required. |
| Degree | Selection | Associate, Bachelor's, Master's, Doctorate, Professional Degree, High School Diploma, GED, Certificate, Other. | Required. |
| Major / Field of Study | Single study field value | One major per education entry, reused for questions about field of study or majors. | Required. |
| Minor | Optional study field value | One minor per education entry. May be omitted or set to None to indicate no minor. No multiple-minor list is specified. | Optional; None is allowed. |
| GPA (Overall Result / Current Cumulative GPA) | GPA value | GPA associated with this education entry, rather than duplicate profile-level GPA fields. Validation is defined in Section 11. | Required; must not be empty. |
| Anticipated Graduation Date | Month and year | Expected graduation date for this education entry. No day component. | May be empty. |
| Education Status | Selection | Currently Studying or Graduated. | Required. |
| Graduation Date | Month and year | Actual graduation date for a Graduated entry; no day component. Not required for a Currently Studying entry. | Required when Graduated; not required when Currently Studying. |

For application fields with predefined options, the selection behavior in Section 10 applies.

## 7. Education Field Reuse

The following application questions use the associated education entry, without requiring duplicate profile inputs:

| Application Question or Value | Education Information Used |
| --- | --- |
| Type of Degree Being Pursued | Degree of the relevant current education entry. This question remains optional; it is not a separate required input. |
| Anticipated Graduation Date | Anticipated Graduation Date in the relevant education entry. |
| Majors | Major / Field of Study in the relevant education entry. |
| Current Cumulative GPA or Overall Result | GPA in the relevant education entry. |
| Already Graduated | Education Status in the relevant education entry. |

The interface must accommodate graduates rather than forcing current-student answers. Education is a list of independent entries, each with its own status, major, minor, and dates. Graduated entries require an actual Graduation Date; Currently Studying entries do not. Anticipated Graduation Date remains optional. Selection of the relevant entry when several exist remains to be designed.

## 8. Skills and Social Network URLs

| Field | Information Type | Description and Rules | Optionality |
| --- | --- | --- | --- |
| Skills | List of skills | Supports zero or more skills. | Empty list allowed. |
| Social Network URLs | List of platform and URL entries | Must support multiple links, including LinkedIn, X, and other social networks. The exact entry structure remains to be defined. | May be omitted. |

## 9. Work Authorization, Compensation, and Demographic Information

| Field | Information Type | Description and Rules |
| --- | --- | --- |
| Legally Authorized to Work in the US | Selection | Yes or No. |
| Employment Visa Sponsorship | Selection | Yes or No. Whether the applicant now or in the future requires sponsorship for an employment visa to work in the United States. |
| Desired Compensation | Free-text user preference | User describes compensation and its basis, such as annual or hourly pay, in their own words. Stored in RAG if the user chooses to persist it; no fixed structured compensation representation is specified. |
| Sex | Selection | Male, Female, Other. |
| Hispanic or Latino | Selection | Yes or No. |
| Race | Single selection | American Indian or Alaska Native; Asian; Black or African American; Native Hawaiian or Other Pacific Islander; White; Two or More Races; Other; Prefer Not to Disclose. Select one option. |
| Veteran Status | Selection | I am not a protected veteran; I identify as a protected veteran; I do not wish to answer. |

All fields in this section are required under the default rule. This draft does not add response categories or default answers.

User-confirmed job preferences are allowed in reusable applicant information and belong in the non-fixed RAG collection. This does not allow subjective narrative application answers to be added to that collection; those remain in historical application records.

## 10. Matching Stored Values to Application Options

When a target application field provides predefined options:

- If a stored value exactly matches an available option, the system may select that option directly.
- If an option is similar but not identical, the system may recommend it for user confirmation or let the user choose from the available options.
- Similarity alone must not be treated as permission to automatically select a non-identical option.

The similarity criteria and detailed recommendation behavior will be defined during implementation design. This rule does not resolve the separate company abbreviation and full-name matching question.

## 11. Input Validation

### 11.1. Default Email

- Must not be empty and must not exceed 254 characters.
- Must contain exactly one `@`, with content on both sides.
- The domain must contain a dot (`.`).
- Must not contain spaces, start or end with a dot, or contain consecutive dots (`..`).
- Characters must be valid for the accepted email format. The exact character policy remains to be specified; no additional character allowlist is introduced here.

### 11.2. United States Phone Number

- Must not be empty.
- May contain only digits and the permitted separators: `+`, `-`, spaces, and parentheses.
- The United States national number must contain 10 digits; an optional `+1` country code may precede it. The optional country code is not part of the 10 national digits.
- Must not contain letters or other special characters.
- The area code must not begin with `0` or `1`.
- Exact separator placement and reconciliation with the separate country-code field remain to be specified.

### 11.3. United States ZIP Code

- Must not be empty.
- Must be either five digits or ZIP+4 in the form `12345-6789`.
- Only digits and the hyphen in the ZIP+4 position are allowed.
- Letters, spaces, and other special characters are not allowed.

### 11.4. GPA

- Must not be empty for any provided education entry. The education list itself may still contain zero entries.
- A supplied numeric value may contain digits and at most one decimal point.
- The value must be between 0.0 and 4.0, inclusive, with at most three decimal places.
- Letters, negative signs, and other special characters are not allowed.

### 11.5. Date Relationships

- Date of Birth must not be in the future.
- When a work experience To value is provided, it must not precede From, comparing their month and year.

## 12. Incomplete Profile Drafts

- The user may save partially completed information as a draft instead of being required to complete all fields immediately.
- Drafts may also contain incorrectly formatted values. Full field validation is required before saving to PostgreSQL, not as a prerequisite for draft retention. Storage exclusions for passwords and verification codes still apply.
- Store the draft as JSON in Redis. Do not create an incomplete applicant profile in PostgreSQL.
- Associate the draft with the user ID established by the system's registration and login module. Use this same ID throughout draft and formal profile storage.
- Retain the Redis draft for seven days. After restarting or reopening the system and logging in, retrieve the unexpired draft by the authenticated user's ID.
- Once the required information is complete and formal saving is approved, save the profile in PostgreSQL using the same user ID.
- Validate the proposed formal profile before SQL saving. Model-based validation, such as Pydantic `BaseModel` validation, may implement the agreed field rules; the exact schema and validators remain to be designed.
- Unconfirmed edits to an existing profile may also be held in Redis. They must not overwrite the saved profile before user confirmation.
- After SQL formal saving succeeds, delete only the corresponding SQL draft version. Do not delete newer edits or independently retained pending RAG contents.
- SQL saving and supplemental RAG saving are separate operations. SQL success counts as its own success independently of RAG. A failed RAG save retains its own pending contents for retry, independently of SQL draft cleanup. See [Supplemental Information](supplemental-information.md).
- If SQL saving fails, retain the draft and return a failure result explaining the reason so the user can correct the relevant information. The frontend should show a visible error indication, such as a red message. Exact presentation remains to be designed.
- Draft storage and formal storage must follow the existing user approval and storage exclusion rules.
- Whether edits restart the seven-day period, Redis restart persistence configuration, and concurrent draft changes remain to be designed. SQL failure must never trigger draft deletion. A profile draft does not resume a cancelled application task.

When formal information exists, use it as the authoritative profile. A draft or proposed conflicting value must not silently replace it. Ask the user to resolve conflicts before changing the formal information. Draft-only recovery remains available when no formal profile exists.

## 13. Items for Subsequent Refinement

- The exact maintained United States state option list.
- Exact address and social URL validation, email character policy, and telephone separator handling.
- Company name equivalence and the relationship between employer history and work experience.
- Month/year serialization; birth dates remain complete year/month/day values.
- Selection among multiple education entries.
- Remaining Redis draft lifecycle details and independent RAG failure reporting and retry behavior.

Existing user approval, conflict handling, real-time profile update versus one-time use, and storage exclusion requirements continue to apply. All operation results must use the shared response envelope; operation-specific data and codes remain to be designed.
