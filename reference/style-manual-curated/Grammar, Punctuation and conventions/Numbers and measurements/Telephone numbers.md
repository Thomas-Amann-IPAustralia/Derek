# Telephone numbers

Write telephone numbers so people can read and use them easily. There are rules for grouping the numbers, using spacing and creating links.

---

## Guidance

- Use ‘chunks’ of digits to help people read telephone numbers  
- Put a non-breaking space between the chunks of digits  
- Write telephone numbers in the national or international format  
- Make telephone numbers accessible through ‘click-to-call’ functionality  
- Don't use ‘phone words’  

---

## Use ‘chunks’ of digits to help people read telephone numbers

Break telephone numbers into shorter blocks of digits or ‘chunks’.

Telephone numbers are easier to read when their digits are chunked, rather than written in one large group.

Australian telephone numbers in general use have no more than 10 digits:

- **Landlines** – 2 digits for the area code followed by 8 digits for the rest of the telephone number.  
- **Mobiles** – 10 digits (there is no area code).  

There are also categories of telephone numbers that don’t have 10 digits – for example, ‘13’ numbers have 6 digits.

**Example**  
> 02 5550 4321 – A landline number in NSW or the ACT  
> 0491 570 159 – An Australian mobile number  
> 1300 975 707 – An Australia-wide local-rate number  
> 13 00 00 – An alternative Australia-wide local-rate number  
> 1800 160 401 – An Australia-wide freephone number  
> +61 2 5550 4321 – An Australian landline number in international format  
> +61 491 570 159 – An Australian mobile number in international format  

---

## Put a non-breaking space between the chunks of digits

Use a non-breaking space between chunks of digits in a telephone number. A non-breaking space means that line breaks won’t split up the number. The telephone number will stay together on one line.

You can insert a non-breaking space using the Unicode character `U+00A0`.

In HTML, use the entity `&nbsp;` to insert a non-breaking space. You can also use the keyboard shortcut **Ctrl+Shift+Spacebar** in Word.

### Print considerations

Use a narrow no-break space between chunks of digits in a telephone number.

The narrow no-break space ensures that the:

- telephone number stays together on one line  
- spacing between digits doesn’t change when text is justified.  

You can insert a narrow no-break space using the Unicode character `U+202F`.

---

## Write telephone numbers in the national or international format

Write telephone numbers in a format appropriate for the location of the users.

### National format for telephone numbers

Use Australia’s national format when writing Australian telephone numbers for content that will be used within Australia.

For **landline telephone numbers**, write the 2-digit area code followed by a non-breaking space. Then write the rest of the number in 2 chunks of 4 digits.

Write **mobile telephone numbers** in 1 chunk of 4 digits and then 2 chunks of 3 digits.

**Example**  
> 02 5550 4321 – Telephone  
> 0491 570 159 – Mobile  

---

### International format for telephone numbers

Use international format for content that will be used outside Australia.

The international format uses a plus symbol ‘+’ to represent the international prefix, followed by a country code (‘61’ for Australia).

For **landline numbers**:

- start with a plus symbol ‘+’ and add the country code (‘61’ for Australia)  
- add the area code without the ‘0’  
- write the telephone number in 2 chunks of 4 digits.

**Example**  
> +61 3 7010 4321 – Landline  

For **mobile numbers**:

- start with a plus symbol ‘+’ and add the country code (‘61’ for Australia)  
- omit the first ‘0’  
- write the telephone number in 3 chunks of 3 digits.

**Example**  
> +61 491 578 888 – Mobile  

Always write foreign telephone numbers in the international format.

**Example**  
> +1 212 555 0188 – US landline  
> +44 20 7946 0990 – UK landline  

---

## Make telephone numbers accessible through ‘click-to-call’ functionality

‘Click-to-call’ allows users to call a telephone number by selecting (clicking) the number shown in content. When the user selects the number, the user’s mobile phone, other mobile device or personal computer (if it has a supporting application) calls the number.

Click-to-call makes telephone numbers more accessible because users don’t need to copy the number manually. Click-to-call also works with screen readers.

Devices sometimes recognise when a number in content is a telephone number and automatically treat the number as a click-to-call link. This is not always the case, so use HTML code to support this functionality. Seek specialist advice if you’re unsure of how to do this.

### Using HTML for click-to-call

Use `tel:[telephone number]` as the URL. Remove spaces between the numbers.

Remember that all webpages can be accessed internationally. Include the international dialling prefix if appropriate.

**Example**  
> 02 5550 5722 – HTML: `<a href="tel:0255505722">02&nbsp;5550&nbsp;5722</a>`  
> 1300 975 7007 – HTML: `<a href="tel:13009757007">1300&nbsp;975&nbsp;7007</a>`  
> 13 83 87 – HTML: `<a href="tel:138387">13&nbsp;83&nbsp;87</a>`  
> 1800 160 401 – HTML: `<a href="tel:1800160401">1800&nbsp;160&nbsp;401</a>`  
> +61 2 7010 0000 – HTML: `<a href="tel:+61270100000">+61&nbsp;2&nbsp;7010&nbsp;0000</a>`  
> +61 491 570 156 – HTML: `<a href="tel:+61491570156">+61&nbsp;491&nbsp;570&nbsp;156</a>`  

---

## Don't use ‘phone words’

Always display the telephone number as digits. Don’t use ‘phone words’. Use the relevant 13 or 1300 number instead.

Some organisations use phone words to advertise their telephone number as a digit-word combination. Don’t do this, because some people find it hard to convert letters to numbers.

**Write this**  
> 13 83 87  

**Not this**  
> 13 VETS  

---

## Release notes

The digital edition expands on information in the sixth edition. It includes examples and has more advice about spaces in telephone numbers.

The sixth edition guidance mentions non-breaking and thin spaces and includes spacing allowances for handwritten telephone numbers on forms.

The *Content Guide* had information about the format of telephone numbers and how to include a clickable link on webpages.
