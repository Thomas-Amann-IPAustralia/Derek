# Proposed matchers against independent sentences

Sentences written by OpenAI without sight of any matcher, labelled blind by Gemini; only those where the two agree are counted. A **miss** is a violating sentence the matcher does not flag; a **false alarm** is a compliant one it does. These are proposals, not ledger examples: nothing here can adopt or unblock a matcher (ADR-027).

| Rule | Agreed (v / c) | Violating caught | Compliant flagged | Near misses flagged | Not agreed |
|---|---|---|---|---|---|
| Don't use commas with Latin shortened forms `c99b24f6` | 8 / 8 | 8/8 | 0/8 | 0/6 | 0 |
| Use commas in numbers with 4 or more digits `8d112f93` | 8 / 8 | 2/8 | 0/8 | 0/6 | 0 |
| Don't use reflexive pronouns such as 'yourself' and 'myself' `eecab3e2` | 8 / 8 | 4/8 | 0/8 | 0/6 | 0 |
| Avoid beginning a sentence with a string of numbers and date `046a4193` | 8 / 8 | 5/8 | 0/8 | 0/6 | 0 |
| Use commas with the phrase 'for example' `6fb92d37` | 8 / 6 | 8/8 | 0/6 | 0/3 | 2 |
| Separate questions tagged onto a sentence `7c4f5c8b` | 8 / 8 | 5/8 | 0/8 | 0/5 | 0 |
| Use numerals and words for large, rounded numbers `abd424c0` | 8 / 8 | 8/8 | 0/8 | 0/6 | 0 |
| Show direct speech or quoted material using commas `72b5baea` | 8 / 5 | 1/8 | 0/5 | 0/3 | 3 |
| Older people `05259592` | 8 / 8 | 8/8 | 0/8 | 0/6 | 0 |

Spend on these sentences: $0.105 OpenAI, $0.233 Gemini.

### Use commas in numbers with 4 or more digits (`8d112f931549bb88`)
- miss: The policy will take effect in 2,027.
- miss: The grant will fund 4800 training places across regional Australia.
- miss: Your approved payment is $27500.
- miss: The dashboard shows 48,00 active accounts.
- miss: The report gives the conversion factor as 0.123,45.
- miss: Please send the completed form to our office in postcode 2,600.

### Don't use reflexive pronouns such as 'yourself' and 'myself' as the subject of the verb. (`eecab3e2f72ea6b8`)
- miss: Yourself can track the application through the online portal.
- miss: Ourselves will send you a replacement card within 10 days.
- miss: Before lodging the application, yourself must check that all required documents are attached.
- miss: Neither the coordinator nor myself will attend the briefing.

### Avoid beginning a sentence with a string of numbers and dates (`046a4193f3fe6331`)
- miss: As at 1 February 2025 32 requests were awaiting a decision.
- miss: Before 31 December 2024 75 grant recipients submitted their final reports.
- miss: On 8 September 2024 64 residents attended the community meeting.

### Use commas with the phrase 'for example' (`6fb92d378b027deb`)
- not agreed (writer: compliant, checker: unclear): The search field accepts the exact phrase ‘for example’. — The phrase 'for example' is mentioned as a quoted string rather than used as a transitional phrase; the section does not settle this mention-versus-use case.
- not agreed (writer: compliant, checker: unclear): The phrase ‘for example’ contains two words. — The phrase is mentioned in quotation marks rather than being used transitionally, which the manual section does not address.

### Separate questions tagged onto a sentence (`7c4f5c8be1bca65e`)
- miss: You haven't received your payment have you?
- miss: The new online booking system was not available during the trial period was it?
- miss: The department did not consult local residents before changing the eligibility criteria did it?

### Show direct speech or quoted material using commas (`72b5baea4fadf9bf`)
- miss: ‘The consultation closes on Friday’ the project coordinator said.
- miss: The adviser asked, ‘Would you like a printed copy.’
- miss: ‘The inspection is complete,’ the manager said, ‘We will publish the findings tomorrow.’
- miss: ‘We can arrange an interpreter’, the receptionist said.
- miss: In the annual report, the director wrote ‘We reduced processing times across all regions.’
- miss: At the policy briefing, the minister said: ‘The changes will protect casual workers.’
- miss: The website editor wrote, ‘You can track your application online’.
- not agreed (writer: compliant, checker: unclear): Select ‘Save’ to keep your changes. — The rule addresses directly quoted speech and whole sentences, not single quoted words like 'Save' without attribution.
- not agreed (writer: compliant, checker: unclear): The review described the process as ‘clear and accessible’. — The rule does not address partial quotations integrated into the flow of the sentence without an introductory verb.
- not agreed (writer: compliant, checker: unclear): The glossary defines ‘applicant’ as a person who applies for a grant. — The rule covers directly quoted speech, not defining terms in quotation marks.

