# Text boxes and callouts

Text boxes, pull-quotes and sidebars draw attention from body text. Make sure they are accessible to everyone.

## Limit the use of text boxes and callouts

You can draw attention to information in content by using text boxes and callouts (pull-quotes and sidebars).

Before you include a text box or callout in your content, consider how it will help people understand or use the information.

Don’t overuse text boxes or callouts: they become a distraction. Avoid putting content in a text box or callout just because you can’t make it fit into the flow of the text.

### Text boxes

Text boxes sit close to the text they support.

Text boxes should contain a summary, examples or an expansion of ideas in the body of the text. This is because people:

- scan text boxes before they read the body text
- often read text boxes separately from the main body of the text.

Use text boxes to set information apart from the content. You can use text boxes for information that is useful but not part of the main content, for example:

- summaries
- checklists
- examples
- case studies
- quotes
- links to related information
- definitions.

### Pull-quotes

Pull-quotes are a type of callout. They are often in the form of an incomplete quote and are set apart with distinct formatting. They are not the same as ‘[block quotations](https://www.stylemanual.gov.au/node/114#format_long_quotes_as_block_quotes_with_no_quotation_marks)’.

Pull-quotes are a device to draw the user back into the content.

#### Example

> ‘engaging with the user is vital in government content’

### Sidebars

Sidebars are a type of callout. They sit beside the main content and are more common in print publications.

## Use text boxes for supporting content, not main text

Text boxes do more than highlight information. They also make it clear that it shouldn’t be read as part of the main text.

Use the same presentation for the same type of content. For example, present example text boxes consistently, but differently to summary information.

Use the same rules for capitalisation, punctuation and lists as other text.

Longer text boxes should have a heading or title to show people the purpose of the text box at a glance. Make it distinct from the other headings in the text so you don’t interrupt the [heading hierarchy](https://www.stylemanual.gov.au/node/51#organise_heading_levels_in_a_logical_order).

In technical or long-form content, text boxes often contain short articles that support the main body of the text. Examples include case studies and descriptions of processes. They often contain [images](https://www.stylemanual.gov.au/node/46).

Number text boxes if they feature repeatedly in content. Refer to numbered text boxes in the body text. You can use an appropriate identifier, such as ‘Box 1’ or ‘Case study 1’.

## Make text boxes accessible in HTML

Make sure boxes are readable by all users and on all devices.

For text boxes in HTML, use the <aside> element.

You can also use the <role=“complementary”> attribute to define an ARIA complementary landmark. Use this when it sits outside the <main> content.

Alternatively, use the <role=“region”> attribute and assign a name if the content needs to sit within the <main> section of a page.

For more information about formatting, visit the World Wide Web Consortium (W3C) [ARIA landmarks example](https://www.w3.org/TR/wai-aria-practices/examples/landmarks/complementary.html).

### Accessibility requirements

User needs:

- I can change the content's presentation without losing information or structure.
- I can find and navigate the content and determine where I am on the webpage.

Fundamentals:

- Organise content in a clear order using section headings.
- Choose colours and fonts that are readable. The design must be able to work well on mobile devices.

Web Content Accessibility Guidelines success criteria:

- [1.3.1 Info and relationships](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=131#info-and-relationships)[–](https://www.w3.org/WAI/WCAG21/quickref/#section-headings)[level A](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=131#info-and-relationships)
- [1.3.2 Meaningful sequence](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=131#meaningful-sequence)[–](https://www.w3.org/WAI/WCAG21/quickref/#section-headings)[level A](https://www.w3.org/WAI/WCAG21/quickref/?showtechniques=131#meaningful-sequence)
- [2.4.10 Section headings – level AAA](https://www.w3.org/WAI/WCAG21/quickref/#section-headings)

## Don’t use text boxes in Microsoft Office documents

You should not use text boxes in Word and PowerPoint. They are not accessible for most users of screen readers.

In Word, text boxes can sit above or below the ‘document layer’ that contains the page text – they are floating objects that can't carry a semantic structure. These features mean that not everyone using a screen reader can:

- read floating objects
- understand how box text relates to page text
- read the box text and page text in the correct order.

Instead of text boxes, use borders and paragraph styles to highlight content visually. If these styles don't work for your content, there are other solutions.

A one-by-one table is an option. If your document has complex formatting, [accessible PDF (Portable Document Format)](https://www.stylemanual.gov.au/format-writing-and-structure/content-formats/pdf-portable-document-format#make_pdf_content_accessible_to_all_users) might be a better option.

Complex Office documents require careful design. To ensure accessibility, get advice from an accessibility professional.
