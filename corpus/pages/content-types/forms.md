# Forms

This guidance helps you to design digital forms filled in by the user. Most of the guidance also applies to printed forms, but there are some differences noted.

## Learn about the user before you design a form

Find out about users and their needs through [user research](https://www.stylemanual.gov.au/node/76). Understand the user and their needs before you design any kind of form (web-based or print).

People use forms to access a service and to meet government requirements.

Sometimes a user will need to fill in a form on behalf of another user. Or a public servant might use a form to record what the user tells them (for example, a statistical survey).

Before you digitise a paper form, make sure you understand the user and business needs. Work out if a form is even needed.

### Find out about language users can relate to

Discover the terms and phrases that people use when they talk about the topic. This includes the words they use in search engines.

Learn about which words will help the user understand the form.

### Develop the ‘question protocol’ first

A ‘question protocol’ is a document that helps you find out what you need to ask the user. It lists:

- the questions you will ask
- why you are collecting information
- what you will do with it.

This document makes it easier to collect the information that is actually needed.

A question protocol also gives you a way to challenge and push back against unnecessary questions. Every time we ask a user for information it costs them and your organisation. It takes time and effort for the user to provide it, and for your organisation to manage it.

Every question protocol is different, but it should answer all the following questions.

Work out what information you need to collect.

- Do you actually need the information? Why?
- How much detail do you need?
- Can you get the information from somewhere else? (For example, it might already be collected in your organisation.)

Explore the experience of the user providing the information.

- Which users need to give you the information?
- How will the user discover or receive the form?
- Will the user need to collect information from other people? (For example, a form can need different people to contribute to it.)
- What happens to the user before and after they give you the information?
- Are there other times you might be collecting related information?

Plan how you will manage the information you will collect.

- How will you check the information is accurate?
- What happens if you get the wrong response? What error messages will you need to provide?
- What will you do with the information when you have it?
- How will you keep the information up to date and secure?

Some of these answers won’t inform the design of the form, but will help you manage the information.

### Information management requirements

Your question protocol becomes a record. So does anything you collect from a form. Records provide evidence of what your organisation has done and why.

Managing and disposing of records properly is a requirement under the [*Archives Act 1983*](https://www.legislation.gov.au/Series/C2004A02796)*.*For guidance, read about the National Archives of Australia’s [information management standards](https://www.naa.gov.au/information-management/information-management-standards).

## Start with one thing per page then test if you need to group

Putting one thing on each page helps you see everything you need to find out, without guessing about the best way to group it.

Begin prototyping with one thing per page over any number of pages:

- one piece of information you’re telling a user
- one decision the user has to make
- one question the user has to answer.

Each question might have more than one field. An address is one thing that would use several fields.

### Example

One question (one thing): the user’s birth date

[In a digital form you you would usually ask this question using 3 fields.]

Having a single thing on each page helps you:

- reduce the cognitive load for users
- save the user’s answers as they move through the form
- capture analytics about each question
- handle branching questions and loops.

Your research with users will help you decide what order to put the questions in. This should include thinking about which topics are more related to each other, or need to be answered by a particular user.

This will help you work out if you need to group questions and create sections.

You might find that you do not need to group any questions.

Keep prototyping and testing the structure of the questions until the user can:

- understand what you’re asking them to do
- focus on the specific question and its answer
- find their way through an unfamiliar process
- use the service on a mobile device.

### Example

A group of 2 fields in a website login

[Users often prefer to have username and password questions on the same page.]

### Avoid using a progress indicator

If the form is short (for example, 5 questions or fewer with no branching), the user won’t need a progress indicator. Adding the indicator would be extra work that the user might not even notice.

It’s difficult to design an accurate indicator that shows a user their progress through a complex form.

Complex forms can branch. They might have sections that don’t apply to some users and optional questions. This means the user might not move through the form in a predictable way.

#### Avoid this

A progress indicator for a registration form

### Test adding task list and ‘check your answers’ pages to complex forms

If you need to help the user estimate how long it will take to fill in a complex form, test adding:

- a task list page at the start
- a ‘check your answers’ page at the end.

Task list pages help users understand the tasks in a transaction and their order.

These pages show the user the tasks they have completed and help them to jump to incomplete tasks.

#### Example

A ‘check your answers’ page summarises the sections of a form. The summary shows the user what information they’ve provided.

This step can help users go back and change any responses, or confirm that they’re giving the correct information.

#### Example

The GOV.UK Design System includes a [check your answers pattern](https://design-system.service.gov.uk/patterns/check-answers/)

## Write clear questions and headings

When you know how to group the questions, you will be able to create the structure.

Organise content in the form using section headings. Describe the topic or the following section in the headings.

Write short active content for forms, including ‘help text’ and error messages – this is called ‘microcopy’.

### Accessibility requirements

User needs:

- I can find and navigate the content and determine where I am on the webpage.
- I can change the content's presentation without losing information or structure.

Fundamentals:

Follow the guidance to write clear questions and headings.

Web Content Accessibility Guidelines success criteria:

- [2.4.6 Headings and labels – level AA](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=248#headings-and-labels)
- [2.4.10 Section headings – level AAA](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=248#section-headings)
- [3.3.2 Labels or instructions – level A](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=248#labels-or-instructions)
- [3.3.6. Error prevention (all) – level AAA](https://www.w3.org/WAI/WCAG21/quickref/#error-prevention-all)

### Use familiar words in familiar ways

Write and design forms starting with [plain language](https://www.stylemanual.gov.au/node/194). Include the terms that are familiar to users.

A form can be harder for people to find and use if it does not contain the terms people expect to be there. Your research with users will identify the terms people use about the topic.

Test the form with the terms included. If they help the user understand and use the form, keep them.

If some users don’t understand the terms, include plain language definitions.

Establish the appropriate [voice and tone](https://www.stylemanual.gov.au/node/40).

### Say who the form is for and what they need

Before a user starts a form, they need to know:

- what the form is for and if they need to fill it in
- who can use the form (if they are eligible for the service)
- what they need to submit the form (for example, tax file number and passport number)
- if they can ask someone else to fill it in for them
- what happens after they submit it and any other stages.

If the form is part of a service that will involve other stages, show the full service process with a task list. Include information about any other forms the user will need to fill in.

### Don’t mark ‘required’ questions – only ask for what you need

You must only collect personal information if it is necessary. Collect the least amount needed for the function or activity related to the form.

Tell people when and why you are collecting their personal information, and what their privacy rights are. Use a collection statement on the form.

You don’t need to mark questions as ‘required’ because you will only be asking for information that is needed.

Sometimes you need to invite the user to tell you something they think is important and they want us to know (for example, to collect feedback). Mark these questions as ‘optional’.

#### Privacy requirements and access to information

When you handle personal information, you must comply with the [Australian Privacy Principles](https://www.oaic.gov.au/privacy/australian-privacy-principles/). Personal information is any information that could identify an individual, in any format.

People have a right to request access to their personal information under the *[Privacy Act 1988](https://www.oaic.gov.au/privacy/the-privacy-act/)*.

People also have the right to request access to government-held information under the *[Freedom of Information Act 1982](https://www.legislation.gov.au/Series/C2004A02562)*. This includes personal information collected in a form.

The federal regulator for privacy and freedom of information legislation is the [Office of the Australian Information Commissioner](https://www.oaic.gov.au/).

### Keep a single column format

Don’t use multiple columns in digital forms.

#### Print considerations

Avoid using a second column in print forms.

If you have to use multiple columns, keep the same number throughout the form.

Make sure the columns are visually different (for example, with a thick line between them).

Splitting information across 2 or more columns can:

- add cognitive load for users
- slow down users of assistive technology if they miss content
- make the form harder to use on mobile devices.

### Number the questions

For forms that have more than one question, number the questions.

This is helpful for the user if they need to leave the form and return to it later. It can also make it easier for them to get help to fill it in, and for them to work across a paper and digital version.

## Choose accessible form inputs

Use the following 3 form inputs. They are the most accessible for users.

If you need the user to:

- pick one preferred option, use radio buttons
- select one or more options, use checkboxes
- write an answer, use a text input (including for numbers).

If you need to use other form inputs, try rewriting the questions to fit these inputs.

### Example

### Radio buttons

A choice of one preferred option

### Example

### Checkboxes

A choice of one or more options

### Example

### Text inputs

Text inputs for a postcode, mobile number and address

Set the size of the text input box to the size of the response the user will provide. Your research will help you work out the right field size.

### Print considerations

There is no way for a user to distinguish between radio buttons and check boxes in print forms. You can include a message to select only one option, but the user might not read this.

Plan for how you will use the information if the user selects more than one option.

Don’t disable inputs as it can confuse the user. Only include a question if it is relevant to the user.

### Avoid this

A text input and a text input field that has been disabled

### Avoid using select (menu items) and range sliders

Select boxes and range sliders can be very hard for some people to use. This includes people who experience essential tremor or difficulties with hand control.

Instead of using a select box, ask other questions to reduce options. Then display fewer options using radio buttons.

#### Like this

Radio buttons

#### Not this

A select box

Use radio buttons instead of range sliders.

#### Like this

Radio buttons

#### Not this

A range slider

### Use buttons for calls to action

Buttons in forms help users carry out an action like submitting or saving a form.

Don’t use a button unless it is a call for action.

The label must clearly describe what happens when the user selects the button. Try to use one word or a short phrase as a label. Avoid using icons or images.

#### Accessibility requirements

User needs:

- I can find and navigate the content and determine where I am on the webpage.
- I can predict the webpage's appearance and how I will operate the content.
- I can operate the webpage with something other than a keyboard, like a pointer.
- I can avoid making any mistakes with my inputs, and correct any that I might make.

Fundamentals:

Follow the guidance to use buttons for calls to action.

Web Content Accessibility Guidelines success criteria:

- [2.4.6 Headings and labels – level AA](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=248#headings-and-labels)
- [3.3.2 Labels or instructions – level A](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=248#labels-or-instructions)
- [2.5.3 Label in name – level A](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=248#label-in-name)
- [1.3.5 Identify input purpose – level AA](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=248#identify-input-purpose)

### Use the primary button for the main action

Use a button for the main call to action on the form (for example, ‘Save and next’ or ‘Send application’).

Position the primary action button in the same place on every page (for example, at the bottom of the form, aligned with the left side of the input field). This placement makes the form predictable and easier to use.

#### Example

A primary button

### Add secondary buttons if there are extra actions

Sometimes you need to use a secondary button for another common action (for example, ‘Save as draft’). Make sure the button action matches what it says it does.

Make secondary buttons visually different and less prominent than the primary button.

#### Example

A primary button and a secondary button

### Avoid using a disabled button

Disabled buttons can confuse some users. Only include them when your research shows they make the form easier for the user.

#### Avoid this

A disabled button

### Write labels for every question

Include one short label for every form question to make it clear to the user what to do. The label is the text that appears near a form question.

Write labels without a colon at the end. Otherwise, follow the normal rules for using [punctuation marks](https://www.stylemanual.gov.au/node/119).

Don’t put anything in the field the user will type in – this is called ‘placeholder text’. Placeholder text disappears when a person clicks in the field and is usually of very low contrast.

Write clear labels and ‘help text’ instead of placeholder text.

#### Example

Label for a text input (‘Email’)

Label for radio buttons (‘Location’)

### Make sure labels are close to their question

Align most labels above and close to the questions.

For numerical fields, place the measurement symbol on the usual side it would be written. For example, put ‘$’ on the left side of the field and ‘%’ on the right side of the field.

Position checkboxes and radio buttons to the left of the label.

### Use <label> or <legend> for digital form headings

If you have one question per page, use that question as the heading for the page.

Put the <label> or <legend> element inside the <h1> element.

This avoids screen readers reading out the same information twice.

#### Example

Create password question

[The question label is also the <H1> heading on this page.]

### Include ‘help text’ to provide more context

Write extra text to help the user complete the question the first time they try. This is called ‘help text’ or ‘hint text’.

In very complex forms, you might need to link to more detailed explanation.

Don’t use ‘tooltips’ to provide help. A tooltip is extra information that appears when the user hovers over an item. It is difficult to design tooltips that everyone can access.

Position the help text between the label and the input field. Don’t use headings, labels or placeholder text for help text.

Associate the help text with the label for screen reader users.

#### Example

Help text for entering a tax file number

### Use prefilled information and default options if appropriate for the user

If it’s appropriate and secure, prefill information. This saves the user time and effort. Research with users to make sure they’re comfortable with prefilling.

Present prefilled information on its own page. Ask the user to check and correct the information as part of the form page.

Never include pre-selected gender or sex options.

#### Example

A request to check contact details

If users are not asked to confirm details they might miss them.

#### Like this

A question about how useful the page is without a default option

#### Not this

A question about how useful the page is with ‘yes’ selected as the default option

[A default option for a satisfaction rating means you can't be sure if the user chose to give this feedback.]

### Add validation to help the user to complete digital forms

A form with validation will check what the user types into fields. It will trigger an error message for the user if they miss a field or make a mistake.

Write error messages so they help the user act on the problem. Do not blame them for making a mistake.

#### Like this

A helpful error message

#### Not this

An unhelpful error message

Apply verification checks for:

- correct numbers of digits – for example, a phone number
- including a required character – for example, the ‘@’ in email addresses.

You can help some users complete the form by adding colour to show if an input is valid. Don’t use colour alone, and make sure assistive technology can detect validation.

If the user is not eligible for a service, don’t show a validation error. Use a separate page that explains:

- why they can’t use the service
- their options.

#### Accessibility requirements

User needs:

I have confidence the markup language supports my use of software and assistive technology to access the content.

Fundamentals:

Follow the guidance to add validation to help the user to complete the digital forms.

Web Content Accessibility Guidelines success criteria:

- [4.1.3 Status messages – level AA](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=248#status-messages)
- [3.3.1 Error identification – level A](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=248#error-identification)
- [3.3.3 Error suggestion – level AA](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=248#error-suggestion)
- [3.3.5 Help – level AAA](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=248#help)
- [3.3.6 Error prevention (all) – level AAA](https://www.w3.org/WAI/WCAG21/quickref/#error-prevention-all)

### Help the user save and resume complex digital forms

Include a button for the user to save a draft as they work through complex forms. The form should reopen to the page they were on.

Display a receipt code when the user submits the form.

### Add only essential branding

Talk to your communications team for guidelines on how to brand forms.

Make sure print and digital forms meet the [Australian Government branding guidelines](https://www.pmc.gov.au/resource-centre/government/australian-government-branding-guidelines-use-australian-government-logo-australian-government-departments-and-agencies).

Only include icons, images or colour when research shows they help the user understand the form. Make sure you create [accessible images](https://www.stylemanual.gov.au/node/46).
