# Applicant Information Management: Input Fields

## 1. Scope and Status

This draft organizes the input fields provided by the project owner for applicant information management. It is a business-level field inventory for review, not a finalized API contract or database schema. Module outputs and detailed processing flows are outside this document's current scope.

Only explicitly stated optional fields and conditional rules are marked as such. Requiredness for other fields remains to be confirmed. Suggested data categories in the tables describe the information; they do not finalize UI controls or technical storage types.

The initial version supports United States addresses and telephone details. Country-dependent labels and validation must be taken into account, but other countries are outside the initial supported scope.

## 2. Identity and Address

| Field | Information Type | Description and Rules | Optionality |
| --- | --- | --- | --- |
| Country | Country selection | Country used to determine address labels and country-specific handling. Only the United States is supported initially. | To be confirmed. |
| First Name | Text | Applicant's first name. | To be confirmed. |
| Last Name | Text | Applicant's last name. | To be confirmed. |
| Preferred Name | Text | Name the applicant prefers to use. | May be empty. |
| Address | Text | Applicant's address. Address labels must depend on the selected country. Initial support is for the United States. | To be confirmed. |
| City | Text | City component of the applicant's address. | To be confirmed. |
| State | State value | State component for United States addresses. The specific input control and available options remain to be defined. | To be confirmed. |
| Postal Code | Postal code value | Postal code component. Labeling must reflect the selected country; United States terminology is ZIP Code. Exact validation rules remain to be defined. | To be confirmed. |
| Date of Birth | Date value | Complete birth date with year, month, and day. Used to calculate accurate age when required. Missing components must be requested rather than estimated. | To be confirmed. |

Age is calculated from the complete date of birth when needed. It is not a separately maintained input field.

## 3. Contact Information

| Field | Information Type | Description and Rules | Optionality |
| --- | --- | --- | --- |
| Email Address | Email value | Must be validated as a correctly formatted email address. Verification of mailbox existence or ownership has not been specified. | To be confirmed. |
| Phone Device Type | Selection | Includes Mobile and other device types. The complete option list has not been defined. | To be confirmed. |
| Country Phone Code | Selection | A country-dependent calling-code list is required. Only the United States calling code is supported in the initial version. | To be confirmed. |
| Phone Number | Telephone value | Must be validated according to the supported country. Initial support is for United States numbers. Exact accepted formats remain to be defined. | To be confirmed. |
| Phone Extension | Extension value | Extension associated with the telephone number. | May be empty. |

The existing requirement for multiple application email addresses with distinct purposes remains applicable. If no separate purpose is specified, the same email address is used. Login email addresses must not be retained as account information.

## 4. Employer History and Company Matching

The system must be able to represent the companies the applicant has worked for. This supports application questions asking whether the applicant has previously worked for the hiring company.

| Item | Description | Status |
| --- | --- | --- |
| Previous Employers | A list of companies for which the applicant has worked. | Initial requirement recorded; detailed representation is pending. |
| Company Name Matching | An abbreviated company name and its full name should be recognizable as the same company. | Matching and user confirmation rules require further design. |
| Relationship to Work Experience | Employer history overlaps with the companies in work experience entries. | Whether it is derived from those entries or managed separately has not been decided. |

No company alias algorithm or automatic conflict-resolution rule is selected in this draft.

## 5. Work Experience

Work experience is a list containing multiple entries. Each entry must support the following fields. Whether each field is mandatory remains to be confirmed except for the stated conditional end-date rule.

| Field per Entry | Information Type | Description and Rules |
| --- | --- | --- |
| Job Title | Text | Title of the role held. |
| Company | Company name | Employer associated with the role. Company abbreviation and full-name matching require further design. |
| From | Date value | Start of the employment period. Required date precision has not been defined. |
| To | Date value | End of the employment period. May be empty when Currently Employed is selected. Other optionality remains to be confirmed. |
| Currently Employed | Selection | Indicates that the applicant is still employed in this role. When selected, To does not need a value. |
| Role Description | Text | Description of the applicant's work in this role. |

## 6. Education

Education is a list containing multiple entries. Each entry must support the following fields.

| Field per Entry | Information Type | Description and Rules |
| --- | --- | --- |
| School or University | Institution value | School or university attended. |
| Degree | Degree value | Degree associated with the education entry. Exact options have not been defined. |
| Field of Study | Study field value | Subject or discipline associated with the education entry. |
| Overall Result (GPA) | GPA value | Overall academic result expressed as GPA. Scale and accepted precision have not been defined. |

For application fields with predefined options, the selection behavior in Section 10 applies. Requiredness of these education fields remains to be confirmed.

## 7. Current Study and Graduation Information

| Field | Information Type | Description and Rules |
| --- | --- | --- |
| Type of Degree Being Pursued | Degree value | Answer to what type of degree the applicant is pursuing. |
| Anticipated Graduation Date | Date value | Expected graduation date. Required date precision remains to be defined. |
| Majors | Major information | Applicant's current major or majors. Detailed representation remains to be defined. |
| Current Cumulative GPA | GPA value | Applicant's current cumulative GPA. Scale and accepted precision remain to be defined. |
| Already Graduated Option | Selection or conditional response | The interface must accommodate applicants who have already graduated, rather than forcing them to answer as current students. Exact options and affected fields will be refined later. |

How these fields relate to individual education entries, and which fields apply to graduates, remains to be determined. Requiredness has not yet been specified.

## 8. Skills and Social Network URLs

| Field | Information Type | Description and Rules | Optionality |
| --- | --- | --- | --- |
| Skills | List of skills | Must support multiple skills. | To be confirmed. |
| Social Network URLs | List of platform and URL entries | Must support multiple links, including LinkedIn, X, and other social networks. The exact entry structure remains to be defined. | May be omitted. |

## 9. Work Authorization, Compensation, and Demographic Information

| Field | Information Type | Description and Rules |
| --- | --- | --- |
| Legally Authorized to Work in the US | User-provided response | Whether the applicant is legally authorized to work in the United States. Exact response options remain to be defined. |
| Employment Visa Sponsorship | User-provided response | Whether the applicant now or in the future requires sponsorship for an employment visa to work in the United States. Exact response options remain to be defined. |
| Desired Compensation | User-confirmed preference | Non-fixed information saved in the supplemental RAG collection when the user chooses to persist it. Currency, pay period, and whether a single amount or range is supported remain to be defined. |
| Sex | User-provided response | Applicant's response to the sex field. Exact options remain to be defined. |
| Hispanic or Latino | User-provided response | Whether the applicant identifies as Hispanic or Latino. Must support a No response indicating that neither applies. Other options remain to be defined. |
| Race | User-provided response | Applicant's response to the race field. Options and whether multiple selections are supported remain to be defined. |
| Veteran Status | User-provided response | Applicant's response to the veteran status field. Exact options remain to be defined. |

Requiredness for the fields in this section has not been specified. This draft does not add response categories or default answers.

User-confirmed job preferences are allowed in reusable applicant information and belong in the non-fixed RAG collection. This does not allow subjective narrative application answers to be added to that collection; those remain in historical application records.

## 10. Matching Stored Values to Application Options

When a target application field provides predefined options:

- If a stored value exactly matches an available option, the system may select that option directly.
- If an option is similar but not identical, the system may recommend it for user confirmation or let the user choose from the available options.
- Similarity alone must not be treated as permission to automatically select a non-identical option.

The similarity criteria and detailed recommendation behavior will be defined during implementation design. This rule does not resolve the separate company abbreviation and full-name matching question.

## 11. Items for Subsequent Refinement

- Required fields, blank-value handling, and complete selection lists.
- Exact address, email, and United States telephone validation rules.
- Company name equivalence and the relationship between employer history and work experience.
- Date precision for employment and graduation, and GPA scales and precision.
- The relationship between current-study fields and education entries, including graduate handling.
- Desired compensation representation.

Existing user approval, conflict handling, real-time profile update versus one-time use, and storage exclusion requirements continue to apply. This draft does not change them or define new module outputs.
