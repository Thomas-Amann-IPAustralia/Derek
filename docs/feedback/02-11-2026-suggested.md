# Accepted rules your 2 November criteria would also hold back

Draft for your review. Each group says which of your own decisions it follows.
Laid out like `docs/feedback/02-11-2026.md`, so you can edit the decision lines in place.
Covers the 1,081 accepted rules on the 99 pages your review didn't reach.

## A. Not a text-drafting rule: publishing, website management or print production

**Following:** cd7f4016 (accessibility statement: 'web governance and publishing advice'), f33cf94a and 829be56e (policy, not style).

**Why:** These are about how a site, periodical or print product is built, not about words a writer drafts. No plain-text input contains a main navigation, a URL slug, a meta description, a cover page or a point size.

**Suggested:** Reject.  (22 rules)

UID: 317e46bf7a9af424
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#317e46bf7a9af424
Rule: links.md | You must include a homepage link in your main navigation.
Suggested decision: Reject.

UID: fd6ea6b98676b9ea
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#fd6ea6b98676b9ea
Rule: links.md | Add homepage links to the agency name or site title
Suggested decision: Reject.

UID: b74510e8f6983442
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#b74510e8f6983442
Rule: journals-magazines-and-newspapers.md | The home page should have:
Suggested decision: Reject.

UID: 0fd812b63c0728b5
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#0fd812b63c0728b5
Rule: page-optimisation.md | Create URLs that contain words from the title of the page with the main keywords close to the start.
Suggested decision: Reject.

UID: 6e6cc2255357e2f0
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#6e6cc2255357e2f0
Rule: page-optimisation.md | The URL should be below 100 characters
Suggested decision: Reject.

UID: 7437c22b71aff8b5
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#7437c22b71aff8b5
Rule: page-optimisation.md | To separate words in the URL, use hyphens instead of spaces or underscores.
Suggested decision: Reject.

UID: 23bb8900f3f14660
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#23bb8900f3f14660
Rule: page-optimisation.md | be different on each page
Suggested decision: Reject.

UID: 1d7667ff2af1596e
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#1d7667ff2af1596e
Rule: page-optimisation.md | They can be up to 160 characters.
Suggested decision: Reject.

UID: 3038fec729c08e9f
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#3038fec729c08e9f
Rule: keywords-and-search-engines.md | Don't use too many keywords or keywords that are outside the context of the content.
Suggested decision: Reject.

UID: 616c4d3ab95805ae
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#616c4d3ab95805ae
Rule: page-optimisation.md | Link to content on other quality sites towards the end of the content.
Suggested decision: Reject.

UID: 534c6b833ce98e77
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#534c6b833ce98e77
Rule: journals-magazines-and-newspapers.md | Include all parts of the periodical
Suggested decision: Reject.

UID: 4b426f50e5a13347
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#4b426f50e5a13347
Rule: journals-magazines-and-newspapers.md | In print and PDF periodicals, start each new volume at page 1.
Suggested decision: Reject.

UID: d6d8bc27302cf6df
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#d6d8bc27302cf6df
Rule: journals-magazines-and-newspapers.md | Repeat all of this information, except for the ISSN, on the first page with the rest of the essential information, such as copyright and any restrictions on cir
Suggested decision: Reject.

UID: c80f85a411bdc9cf
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#c80f85a411bdc9cf
Rule: journals-magazines-and-newspapers.md | Put the publication details for each issue on the cover page.
Suggested decision: Reject.

UID: a2794d81aba60f0e
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#a2794d81aba60f0e
Rule: journals-magazines-and-newspapers.md | Put this extra information on page 2 (with the contents list) or the back page:
Suggested decision: Reject.

UID: 1c3a66c5a0f3585a
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#1c3a66c5a0f3585a
Rule: journals-magazines-and-newspapers.md | Include the title, date and page number at the top or bottom of the page.
Suggested decision: Reject.

UID: 227e23fbdc49eae9
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#227e23fbdc49eae9
Rule: video-and-audio.md | Provide a text alternative to video and audio
Suggested decision: Reject.

UID: 4f17d58ae052cf79
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#4f17d58ae052cf79
Rule: tables.md | Don't use a point size that is too small.
Suggested decision: Reject.

UID: 11fc85adbfc21795
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#11fc85adbfc21795
Rule: tables.md | Try to keep tables on one page.
Suggested decision: Reject.

UID: ffdb38e63df54cca
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#ffdb38e63df54cca
Rule: tables.md | If a table runs over pages when printed, ensure:
Suggested decision: Reject.

UID: fff1c77ef4fbd678
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#fff1c77ef4fbd678
Rule: tables.md | Use the same font, and font sizes, rule (line) thicknesses and colour schemes for tables throughout the document.
Suggested decision: Reject.

UID: 3e5c6fbc65e75396
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#3e5c6fbc65e75396
Rule: tables.md | Don't rotate text to display vertically.
Suggested decision: Reject.

## B. Non-breaking spaces: the input and the gate can't see them

**Following:** none directly, but this is the strongest technical case in the list.

**Why:** derek/corpus/normalise.py:130 replaces every non-breaking space with an ordinary one, so the dogfood gate reads the manual's own prose as breaking all ten rules at every date, time, unit and phone number. That is Octavius's failure exactly (D-1, D-14). Their violating fixtures were already removed in the October review (R02).

**Suggested:** Backlog until a format-aware adapter exists (D-13).  (10 rules)

UID: 5a0aa27339eb0a46
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#5a0aa27339eb0a46
Rule: dates-and-time.md | Insert a non-breaking space between the day and the month so they stay together on one line.
Suggested decision: Backlog until a format-aware adapter exists (D-13).

UID: af050089f499c7a4
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#af050089f499c7a4
Rule: dates-and-time.md | Use 2 non-breaking spaces to keep each name together on one line of text.
Suggested decision: Backlog until a format-aware adapter exists (D-13).

UID: 05f1727e4e69bca4
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#05f1727e4e69bca4
Rule: dates-and-time.md | Separate the numbers and the initialism with a non-breaking space.
Suggested decision: Backlog until a format-aware adapter exists (D-13).

UID: 00253d0525d6c2a3
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#00253d0525d6c2a3
Rule: dates-and-time.md | If your expression contains one time measure only, insert a non-breaking space between the number and unit.
Suggested decision: Backlog until a format-aware adapter exists (D-13).

UID: 80b00b6efd9a4d49
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#80b00b6efd9a4d49
Rule: dates-and-time.md | Use a non-breaking space between each time value instead.
Suggested decision: Backlog until a format-aware adapter exists (D-13).

UID: aac9c327932ae12d
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#aac9c327932ae12d
Rule: mathematical-relationships.md | Insert a non-breaking space between numbers, letters and the symbol for an operator or a relation.
Suggested decision: Backlog until a format-aware adapter exists (D-13).

UID: e35db09caa44acff
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#e35db09caa44acff
Rule: measurement-and-units.md | Put a non-breaking space between numbers and units
Suggested decision: Backlog until a format-aware adapter exists (D-13).

UID: e8605c124ef7c4dc
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#e8605c124ef7c4dc
Rule: ordinal-numbers.md | Use a non-breaking space for names with regnal numbers
Suggested decision: Backlog until a format-aware adapter exists (D-13).

UID: 353e6a05dd71c918
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#353e6a05dd71c918
Rule: telephone-numbers.md | Put a non-breaking space between the chunks of digits
Suggested decision: Backlog until a format-aware adapter exists (D-13).

UID: 1ec4553927952de3
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#1ec4553927952de3
Rule: personal-names.md | Use non-breaking spaces to ensure that initials are not separated from family names.
Suggested decision: Backlog until a format-aware adapter exists (D-13).

## C. Needs markup or visual formatting the plain-text input doesn't carry

**Following:** 1b144afc (<figcaption>), f88feb82 (<longdesc>), 8d608584 (logo links): 'further consideration must be given to how we might enforce this rule'.

**Why:** HTML elements, link targets, colour, alignment, underline, superscript, fonts and print pagination can't be seen in a plain-text Document (D-13).

**Suggested:** Backlog.  (26 rules)

UID: 2097fddb2df8d993
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#2097fddb2df8d993
Rule: plants-and-animals.md | Use the semantic tag <em> to provide emphasis for italicised names in HTML.
Suggested decision: Backlog.

UID: 47f9ec36b9beb224
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#47f9ec36b9beb224
Rule: headings.md | Use styles, tags and HTML elements to identify headings in digital content.
Suggested decision: Backlog.

UID: 207db8caea829db6
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#207db8caea829db6
Rule: headings.md | Use just one level 1 heading per webpage.
Suggested decision: Backlog.

UID: b025069adb262202
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#b025069adb262202
Rule: tables.md | Mark up tables to show header cells and data cells.
Suggested decision: Backlog.

UID: 1976b0c9ea753af6
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#1976b0c9ea753af6
Rule: tables.md | If you use a complex table, you must define the column and row groups and mark up the table accordingly.
Suggested decision: Backlog.

UID: 0498a44d7df66e89
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#0498a44d7df66e89
Rule: tables.md | Don't make tables with other tables inside them (known as 'nested'tables).
Suggested decision: Backlog.

UID: 22da7715a046adcb
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#22da7715a046adcb
Rule: tables.md | Avoid using them in word processing applications.
Suggested decision: Backlog.

UID: c2c241128978a9fc
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#c2c241128978a9fc
Rule: telephone-numbers.md | Remove spaces between the numbers.
Suggested decision: Backlog.

UID: 53c8c62279f24baf
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#53c8c62279f24baf
Rule: links.md | In all cases, give users contextual information in the link to explain why a link will open in a new window or tab.
Suggested decision: Backlog.

UID: 9f58aa3f3cbee08f
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#9f58aa3f3cbee08f
Rule: documentary-note.md | In digital content, hyperlink the reference marker to help users access the note.
Suggested decision: Backlog.

UID: 737cd8751a14e953
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#737cd8751a14e953
Rule: legal-material.md | Use hyperlinked endnotes in digital content.
Suggested decision: Backlog.

UID: 9286aede1671c6e9
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#9286aede1671c6e9
Rule: tables.md | Don't rely on colour as the only visual means of conveying information in tables.
Suggested decision: Backlog.

UID: 3c8d639ad6a66e76
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#3c8d639ad6a66e76
Rule: tables.md | In addition, decimal points in the column should line up.
Suggested decision: Backlog.

UID: c4f3783d4947f669
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#c4f3783d4947f669
Rule: tables.md | Don't use cell or text formatting to convey meaning.
Suggested decision: Backlog.

UID: 57041639559f5d27
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#57041639559f5d27
Rule: headings.md | Don't underline headings or any other text.
Suggested decision: Backlog.

UID: d8fcdcca82b575cb
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#d8fcdcca82b575cb
Rule: australian-place-names.md | without punctuation or underlining
Suggested decision: Backlog.

UID: 78cd75a3f35eae3f
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#78cd75a3f35eae3f
Rule: tables.md | Don't use superscript for the note identifiers (the symbol, number or letter) in the note.
Suggested decision: Backlog.

UID: ccd4aa7d9c58da7c
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#ccd4aa7d9c58da7c
Rule: ordinal-numbers.md | Don't write suffixes in superscript.
Suggested decision: Backlog.

UID: 80a73b44915da916
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#80a73b44915da916
Rule: mathematical-relationships.md | There is no space between a character and its superscript or subscript.
Suggested decision: Backlog.

UID: 380f96cbb58b6187
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#380f96cbb58b6187
Rule: quotation-marks.md | The surrounding text determines the font (roman, italic, or bold) of the quotation marks.
Suggested decision: Backlog.

UID: 24477c0c3e14b538
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#24477c0c3e14b538
Rule: brackets-and-parentheses.md | Write brackets in the same type as the surrounding text
Suggested decision: Backlog.

UID: 512f4670d940634e
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#512f4670d940634e
Rule: documentary-note.md | Restart the symbols on each page.
Suggested decision: Backlog.

UID: 6eb85ede5306e8ee
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#6eb85ede5306e8ee
Rule: documentary-note.md | In content that uses a lot of citations, restart numbering on each page of digital content or in each section of a document.
Suggested decision: Backlog.

UID: 9c2c4c5eeab69090
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#9c2c4c5eeab69090
Rule: documentary-note.md | In print, if you have sections written by different authors or on different subjects, include a list of endnotes at the end of each section.
Suggested decision: Backlog.

UID: bad2491ab1b6e0e6
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#bad2491ab1b6e0e6
Rule: headings.md | If you use numbered headings, use them only in the body.
Suggested decision: Backlog.

UID: ae3c224c35937e5a
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#ae3c224c35937e5a
Rule: headings.md | Don't number more than the first 3 heading levels.
Suggested decision: Backlog.

## D. Already marked not_automatable, but still accepted

**Following:** your Mx decision (fee045ca: 'difficult to have enough context'); docs/09 gives this clarity to rules that can only be judged against a source the text doesn't carry.

**Why:** The October review's own gate blocks a matcher for a clarity no matcher can implement. So these rules can never be detected, yet they count as live.

**Suggested:** Backlog (or reject).  (6 rules)

UID: e7fd182ff11e428a
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#e7fd182ff11e428a
Rule: quotation-marks.md | If you use ellipses for omitted words, ensure that the omission won't mislead readers about the content or tone of the source you're quoting.
Suggested decision: Backlog (or reject).

UID: 6b2b2281c19ddc9e
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#6b2b2281c19ddc9e
Rule: quotation-marks.md | If the quotation needs the information for context, add specific detail in square brackets.
Suggested decision: Backlog (or reject).

UID: 7ce25fb67fe032ad
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#7ce25fb67fe032ad
Rule: quotation-marks.md | In quoted material use the original spelling of the quoted material, even if it uses US spellings such as 'color'.
Suggested decision: Backlog (or reject).

UID: 33b5541771931633
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#33b5541771931633
Rule: reports.md | Australian Government reports published online should include the same information as a printed version.
Suggested decision: Backlog (or reject).

UID: c67ab63e9e264eb6
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#c67ab63e9e264eb6
Rule: reports.md | Each volume should have a summary list of the contents of the other volumes in the set.
Suggested decision: Backlog (or reject).

UID: 478fff6356a906e3
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#478fff6356a906e3
Rule: paragraphs.md | Put paragraphs in the order that makes sense to the user
Suggested decision: Backlog (or reject).

## E. Needs knowledge from outside the text

**Following:** fee045ca (Mx), 94824db3 (whether a form is designed to collect it), 66fd2fd9 and 653ba910 (attachments, signature blocks).

**Why:** Each rule turns on a fact Derek doesn't have: how a person or organisation writes its own name, what the original source says, an official register, or who the letter is going to. Most are tagged 'unambiguous', but by the docs/09 reading they are not_automatable.

**Suggested:** Backlog.  (29 rules)

UID: a208f3bc4481bb0b
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#a208f3bc4481bb0b
Rule: personal-names.md | When you write to or about people, always use the form of personal name that the person uses.
Suggested decision: Backlog.

UID: 6e312e300c828fe9
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#6e312e300c828fe9
Rule: personal-names.md | When you write names, retain diacritic marks unless the person commonly uses a simplified form of their name.
Suggested decision: Backlog.

UID: 39bda8748c81df79
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#39bda8748c81df79
Rule: organisation-names.md | Write the name as the organisation writes it
Suggested decision: Backlog.

UID: 161256d010a38ad4
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#161256d010a38ad4
Rule: medical-terms.md | Always refer to organisations in the same way as they refer to themselves.
Suggested decision: Backlog.

UID: ca023123f6e684c9
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#ca023123f6e684c9
Rule: organisation-names.md | Use the organisation's shortened form only if the organisation regularly uses it in its own content.
Suggested decision: Backlog.

UID: 5c93ab9f815db30d
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#5c93ab9f815db30d
Rule: apostrophes.md | Use an apostrophe if the organisation does.
Suggested decision: Backlog.

UID: 8d508adb2c9f4f52
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#8d508adb2c9f4f52
Rule: organisation-names.md | If you cite a source written by an organisation that has since changed its name, use the name that was published in the source.
Suggested decision: Backlog.

UID: 539c91915221109d
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#539c91915221109d
Rule: author-date.md | Use the same capitalisation as the organisation uses for the name of a website.
Suggested decision: Backlog.

UID: b76fa615bc884fab
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#b76fa615bc884fab
Rule: documentary-note.md | Use the same capitalisation as the organisation uses for the name of a website.
Suggested decision: Backlog.

UID: c7e2ca90fc289b94
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#c7e2ca90fc289b94
Rule: works-art.md | use the same capitalisation as the museum or gallery uses.
Suggested decision: Backlog.

UID: 139653eafead195b
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#139653eafead195b
Rule: plays-and-poetry.md | Capitalise and punctuate the title of a poem as the author does
Suggested decision: Backlog.

UID: 37a9e5af05ebbad4
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#37a9e5af05ebbad4
Rule: author-date.md | Use the original spelling for all author names.
Suggested decision: Backlog.

UID: 4f3bf6ce4fdb1c82
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#4f3bf6ce4fdb1c82
Rule: documentary-note.md | Use the original spelling for all author names.
Suggested decision: Backlog.

UID: 6e5e1810dad3dd45
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#6e5e1810dad3dd45
Rule: author-date.md | Use the original spelling for all titles and periodical names.
Suggested decision: Backlog.

UID: 8ff8ead1f0a7b304
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#8ff8ead1f0a7b304
Rule: documentary-note.md | Use the original spelling for all titles and periodical names.
Suggested decision: Backlog.

UID: b09ab2daf2fe072d
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#b09ab2daf2fe072d
Rule: documentary-note.md | Use the name that appears on the source.
Suggested decision: Backlog.

UID: d8085fa9dd181bf3
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#d8085fa9dd181bf3
Rule: acts-parliament.md | If the Act's title has a number, include the number exactly as written.
Suggested decision: Backlog.

UID: ac2cbc1af8338c0a
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#ac2cbc1af8338c0a
Rule: acts-parliament.md | Include all the words in the title.
Suggested decision: Backlog.

UID: bf0f0ad0d3945310
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#bf0f0ad0d3945310
Rule: punctuation-and-capitalisation.md | In these cases, use the form of the name as it is written in the legislation.
Suggested decision: Backlog.

UID: 72e5b27899ef6ae1
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#72e5b27899ef6ae1
Rule: ellipses.md | If there is an ellipsis in the original text you're quoting, add the phrase 'ellipsis in original' in square brackets after the quote.
Suggested decision: Backlog.

UID: c64e595d1c5b94ad
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#c64e595d1c5b94ad
Rule: authoritative-reports.md | Cite an authorised law report if one is available
Suggested decision: Backlog.

UID: fb3746418a82521d
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#fb3746418a82521d
Rule: australian-place-names.md | The order should be as written in the official name, which you can check in the Australian Place Names dataset.
Suggested decision: Backlog.

UID: 90d65e35b3d2a064
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#90d65e35b3d2a064
Rule: spelling.md | Always use the first entry in the list.
Suggested decision: Backlog.

UID: 2aa665db9cea310a
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#2aa665db9cea310a
Rule: works-art.md | When you write about artwork, include the name of the institution that holds the work in its collection.
Suggested decision: Backlog.

UID: 9cd8726fe8b8f803
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#9cd8726fe8b8f803
Rule: academics-and-professionals.md | If the holder of a doctorate is knighted, don't address them as 'Doctor'.
Suggested decision: Backlog.

UID: 82363a07ce1c8691
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#82363a07ce1c8691
Rule: academics-and-professionals.md | Use 'Doctor' or 'Dr' for medical practitioners, dentists and veterinarians, whether or not they hold a doctorate.
Suggested decision: Backlog.

UID: 050c5dc96f8222bc
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#050c5dc96f8222bc
Rule: royalty-vice-royalty-and-nobility.md | Address letters to the King to his private secretary.
Suggested decision: Backlog.

UID: 906b6227357df023
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#906b6227357df023
Rule: royalty-vice-royalty-and-nobility.md | Address correspondence to the Governor-General to the Official Secretary at Government House, Canberra.
Suggested decision: Backlog.

UID: f4b10d323a79597b
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#f4b10d323a79597b
Rule: judiciary.md | When addressing an envelope use 'Her Honour Magistrate' or 'His Honour Magistrate'.
Suggested decision: Backlog.

## F. Too abstract to enforce consistently

**Following:** 3634c385, 196e292a, dc5e1be3, c6824d15, 7a42631c, 9183d970: 'too abstract' or 'requires determining relevance'.

**Why:** Each turns on whether something is relevant, essential, logical, clear or suited to the reader. Of the 16 rules in your review tagged ambiguous_deferred, 15 were not accepted. Most of these share that tag.

**Suggested:** Backlog.  (35 rules)

UID: ad3462fdb644e307
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#ad3462fdb644e307
Rule: paragraphs.md | Limit each paragraph to one topic
Suggested decision: Backlog.

UID: c1b6c019b357e6a6
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#c1b6c019b357e6a6
Rule: paragraphs.md | Expand on the heading in the first paragraph
Suggested decision: Backlog.

UID: 5c82fe0520b20d1d
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#5c82fe0520b20d1d
Rule: paragraphs.md | The first sentence in each paragraph should be a topic or transition sentence.
Suggested decision: Backlog.

UID: 8848da99145e072f
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#8848da99145e072f
Rule: types-structure.md | Write clear page titles.
Suggested decision: Backlog.

UID: fa908391d8e31732
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#fa908391d8e31732
Rule: types-structure.md | Use a logical hierarchy or sequential steps for headings.
Suggested decision: Backlog.

UID: 7de8d404de44e31f
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#7de8d404de44e31f
Rule: types-structure.md | Start with the most important idea first.
Suggested decision: Backlog.

UID: 973048ec1f87b9e1
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#973048ec1f87b9e1
Rule: inverted-pyramid-structure.md | For long-form content, use a summary or a list of recommendations in the preliminary pages.
Suggested decision: Backlog.

UID: c1501dd3b5216068
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#c1501dd3b5216068
Rule: narrative-structure.md | Omit anything that isn't related to your primary message.
Suggested decision: Backlog.

UID: 24eea6b8f4f96fb2
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#24eea6b8f4f96fb2
Rule: narrative-structure.md | There must be a logical connection between the 3 parts.
Suggested decision: Backlog.

UID: 1c665178b903ac03
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#1c665178b903ac03
Rule: sequential-structure.md | For example, instructions and transactions are more direct and use the imperative.
Suggested decision: Backlog.

UID: e459775a31afdf7a
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#e459775a31afdf7a
Rule: sequential-structure.md | Reports of events usually use the past tense of the verb.
Suggested decision: Backlog.

UID: 83e1aed284173249
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#83e1aed284173249
Rule: adjectives.md | Use adjectives sparingly and only when they are essential for meaning.
Suggested decision: Backlog.

UID: 5ea53bb48d5b5b9f
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#5ea53bb48d5b5b9f
Rule: adverbs.md | Remove any adverb that doesn't play a critical function in a sentence.
Suggested decision: Backlog.

UID: 94af14a98b619b3f
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#94af14a98b619b3f
Rule: determiners.md | Don't use 'the' when you make a generalisation.
Suggested decision: Backlog.

UID: 75f51f73750c7338
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#75f51f73750c7338
Rule: sentences.md | Write exactly what you mean and construct your sentences so there is no ambiguity.
Suggested decision: Backlog.

UID: 113a77ae31f79aab
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#113a77ae31f79aab
Rule: sentences.md | Eliminate unnecessary words
Suggested decision: Backlog.

UID: 68bc6ad6b6bb7f7a
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#68bc6ad6b6bb7f7a
Rule: plain-language-and-word-choice.md | Use personal pronouns (like 'we', 'you', 'us') when it suits the voice and tone.
Suggested decision: Backlog.

UID: e20d597c20709475
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#e20d597c20709475
Rule: plain-language-and-word-choice.md | Shorten only the words and phrases that are well known or used many times in your content.
Suggested decision: Backlog.

UID: 6c20cc594f486a42
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#6c20cc594f486a42
Rule: video-and-audio.md | Ensure audio and supporting text use inclusive language.
Suggested decision: Backlog.

UID: dbb247617a2c1f65
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#dbb247617a2c1f65
Rule: video-and-audio.md | Use simple language and a conversational tone, and avoid jargon.
Suggested decision: Backlog.

UID: c1f961bb113bf4c5
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#c1f961bb113bf4c5
Rule: links.md | Link to something only if it helps meet the user's need
Suggested decision: Backlog.

UID: 52bad54a1fae2250
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#52bad54a1fae2250
Rule: links.md | Include keywords at the start of links
Suggested decision: Backlog.

UID: 412d3cc251d7c51d
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#412d3cc251d7c51d
Rule: links.md | If it's important for users to understand all your content, put links at the end of sentences.
Suggested decision: Backlog.

UID: e545b539907820e5
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#e545b539907820e5
Rule: exclamation-marks.md | Use them sparingly in less formal content such as promotional material and social media posts.
Suggested decision: Backlog.

UID: 801d4fdf97903bbc
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#801d4fdf97903bbc
Rule: academics-and-professionals.md | Use full titles in certain contexts
Suggested decision: Backlog.

UID: 7f93bfdac2b0501b
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#7f93bfdac2b0501b
Rule: academics-and-professionals.md | Only use shortened forms of titles in limited circumstances.
Suggested decision: Backlog.

UID: dce0cd54704eda8a
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#dce0cd54704eda8a
Rule: nationalities-peoples-and-places-outside-australia.md | Use a short form of a country's name only if it's clear and accurate.
Suggested decision: Backlog.

UID: ced28840b20c7650
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#ced28840b20c7650
Rule: italics.md | Don't use italics when another style or formatting option is available.
Suggested decision: Backlog.

UID: a2617ca0addfbcc4
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#a2617ca0addfbcc4
Rule: commas.md | Check if you can rephrase the information to make it easier to follow.
Suggested decision: Backlog.

UID: 2563db5fe96c4968
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#2563db5fe96c4968
Rule: abbreviations.md | Limit the use of abbreviations
Suggested decision: Backlog.

UID: 328b6e20d7abaa9d
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#328b6e20d7abaa9d
Rule: abbreviations.md | If there's any doubt, define the abbreviation on first use.
Suggested decision: Backlog.

UID: c6200d96e793f9eb
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#c6200d96e793f9eb
Rule: reports.md | For long reports, use a summary to present findings, recommendations and conclusions.
Suggested decision: Backlog.

UID: 1902f1ef7ad5c7c6
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#1902f1ef7ad5c7c6
Rule: reports.md | Both chapters and parts need short titles that tell the user what is in the content.
Suggested decision: Backlog.

UID: 934c251d514d364e
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#934c251d514d364e
Rule: reports.md | Use a glossary to explain specialist or unfamiliar terms.
Suggested decision: Backlog.

UID: 887a1c984c52d9b4
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#887a1c984c52d9b4
Rule: reports.md | Wherever it features, people should be able to easily find copyright and other information about the report.
Suggested decision: Backlog.

## G. Borderline: 'only if space is limited'

**Following:** the same judgement call as F, but narrower.

**Why:** These depend on whether space is limited. A table or list block could stand in for that, so they may be salvageable with a precondition.

**Suggested:** Your call: backlog, or keep with a block-type precondition.  (5 rules)

UID: 9707df549674b337
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#9707df549674b337
Rule: dates-and-time.md | Only use short forms if space is limited and the short forms are easy to identify correctly.
Suggested decision: Your call: backlog, or keep with a block-type precondition.

UID: 5a70ed5146c12995
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#5a70ed5146c12995
Rule: dates-and-time.md | Only use en dashes for time spans if you have limited space.
Suggested decision: Your call: backlog, or keep with a block-type precondition.

UID: 5d0f740c1ac16d1b
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#5d0f740c1ac16d1b
Rule: dates-and-time.md | Don't use shortened forms, such as 18C or C18, unless you have limited space.
Suggested decision: Your call: backlog, or keep with a block-type precondition.

UID: 76869c684501ddea
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#76869c684501ddea
Rule: topographic-terms.md | Use the abbreviated form only where there's limited space or a lot of repetition, such as in tables and maps.
Suggested decision: Your call: backlog, or keep with a block-type precondition.

UID: e59458afa5b29c4f
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#e59458afa5b29c4f
Rule: measurement-and-units.md | Spell them out in full – unless they're in a table, list or chart and are easy to understand.
Suggested decision: Your call: backlog, or keep with a block-type precondition.

## H. Report and document structure, and numbering

**Following:** the forms backlog ('further consideration must be given to management of forms') and the figure-numbering backlog (3f117a7e, f4ab81d1, 8d74e7c1, e9751a8b).

**Why:** These are about the parts, pages and numbering of a whole report: title pages, half-titles, roman-numeral prelims, volume pagination, table numbering. A pasted passage has none of it. The report rules about wording are left out of this list and can stay: 19471ffd 'Contents', aba12446 'Executive summary', d96bc0dd, 11fa7e79, b4090bd4.

**Suggested:** Backlog until 'report' is handled the way you're planning for forms and correspondence.  (21 rules)

UID: 882d7dbc9e0583a4
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#882d7dbc9e0583a4
Rule: reports.md | Order the parts of the report
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 9e48e1fd0a29c78e
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#9e48e1fd0a29c78e
Rule: reports.md | Use the landing page or cover to identify the report
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 4dce318916135ddb
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#4dce318916135ddb
Rule: reports.md | A title page should include the following:
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 13799b0067fd7829
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#13799b0067fd7829
Rule: reports.md | Conventions for a half-title page are:
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: ccdc0c2c4b0879db
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#ccdc0c2c4b0879db
Rule: reports.md | Number them with lower case roman numerals such as 'i', 'ii', 'iii' and 'iv'.
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 29d62935359ca66c
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#29d62935359ca66c
Rule: reports.md | Give each image a page number in the list.
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 4ab734d5af290fe4
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#4ab734d5af290fe4
Rule: reports.md | The order of lists is:
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 4ce003e6112362e2
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#4ce003e6112362e2
Rule: reports.md | Page numbering for the endmatter continues from the main body of the report.
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 1996fd5bab5c01a8
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#1996fd5bab5c01a8
Rule: reports.md | If there are several appendices, use a title page.
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 94e990f51bc04cf9
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#94e990f51bc04cf9
Rule: reports.md | Always number preliminary pages per volume.
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: c215bfdb3ad2d804
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#c215bfdb3ad2d804
Rule: reports.md | Where numbering restarts for each volume, references should include both the volume and page number.
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 7de1217c977e2303
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#7de1217c977e2303
Rule: reports.md | Don't use roman numerals to number parts.
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 8f9948d6144ed0f6
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#8f9948d6144ed0f6
Rule: reports.md | If the list is brief, include it in the preliminary content.
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: c0e1ae3f3638c864
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#c0e1ae3f3638c864
Rule: reports.md | is always in the preliminary content
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 03c9406b4b15ffb5
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#03c9406b4b15ffb5
Rule: reports.md | should be in the main part of the report if people will need the content to understand the report – for example, if the introduction includes terms of reference
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 47374fc8511ce3c2
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#47374fc8511ce3c2
Rule: reports.md | Number appendices differently from how chapters are numbered in the report.
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 2a31743d874aa811
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#2a31743d874aa811
Rule: reports.md | Use consecutive numbering for chapter titles through the report.
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: a589c185a9391284
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#a589c185a9391284
Rule: reports.md | Always place a bibliography after a reference list or endnotes if the report has both.
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 540b1580851faee5
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#540b1580851faee5
Rule: tables.md | number tables
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: dd3db482b8181ec1
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#dd3db482b8181ec1
Rule: tables.md | Ensure that the table number referenced in the text matches the table number in the title.
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

UID: 612e32dd8aaf15bb
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#612e32dd8aaf15bb
Rule: text-boxes-and-callouts.md | Number text boxes if they feature repeatedly in content.
Suggested decision: Backlog until 'report' is handled the way you're planning for forms and correspondence.

## I. Overlaps to consolidate

**Following:** b78a9d9b into 07e6789d; a0f9e70a with 52e114e9.

**Why:** 4f5ab1e7's 15-word average is f3fb9963 (accepted) again, with a 25-word cap added. 1817cc8f's 2–3 sentence paragraphs cover 514d16fb's blog rule (accepted) for all content, so one blog paragraph is flagged twice.

**Suggested:** Consolidate 4f5ab1e7 into f3fb9963, and 1817cc8f with 514d16fb.  (2 rules)

UID: 4f5ab1e7b530ffde
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#4f5ab1e7b530ffde
Rule: sentences.md | Keep sentences to an average of 15 words and no more than 25 words, especially for digital content.
Suggested decision: Consolidate 4f5ab1e7 into f3fb9963, and 1817cc8f with 514d16fb.

UID: 1817cc8ff2f7fe6b
Link: https://thomas-amann-ipaustralia.github.io/Derek/inspect/#1817cc8ff2f7fe6b
Rule: paragraphs.md | Keep most paragraphs to 2 or 3 sentences
Suggested decision: Consolidate 4f5ab1e7 into f3fb9963, and 1817cc8f with 514d16fb.

## J. Structural: referencing rules don't know which system the document uses

author-date.md and its sub-pages have 170 accepted rules, and documentary-note.md has 76. All have `applies_to: [any]`, and only about 29 say which system they belong to.
With both sets live, a correct reference in one system breaks the other system's rules.
For example, 38620cc7 (author-date: family name before initials) and 079fa019 (documentary-note: initials before family name) contradict each other on the same name.
This is R08 in docs/09: the engine has no document context to check against. The fix would be a 'referencing system' choice, like the audience and correspondence choices you're planning for the GUI.
Until then, these rules should not go live together.
