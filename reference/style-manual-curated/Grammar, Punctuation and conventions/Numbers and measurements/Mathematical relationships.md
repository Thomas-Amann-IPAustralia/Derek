# Mathematical relationships

A mathematical relationship is the connection between sets of numbers or variables. In most content, the connection should be described in words. Only use symbols if there’s a user need. Code symbols correctly to ensure they are accessible.

---

## Guidance

- Use words instead of symbols to improve accessibility  
- Use symbols when user research supports their use  
- Use a non-breaking space to keep characters and symbols together  
- Don’t use a space if a symbol modifies a value  
- Use the correct style for equations  

---

## Use words instead of symbols to improve accessibility

In most content, explain mathematical relationships using words instead of symbols.

Many people will understand simple operations written with symbols (`1 + 1 = 2`). But other mathematical relationships are hard to understand unless they are written in words. Symbols might not be available in every font set and the default settings of screen readers might not read all symbols.

Some users are unfamiliar with mathematical terminology. Make sure that you explain terms and concepts in plain language.

This rule applies to general content. If you’re writing specialist mathematical and scientific content, follow your publisher’s style.

In all mathematical expressions, write numbers as numerals. This applies even when you use words to explain a relationship between the numbers.

**Write this**  
> The square root of 56 is greater than the square root of 26.  
> We can prove that 0 does not equal 1.

**Not this**  
> √56 > √26.  
> We can prove that 0 ≠ 1.  
> We can prove that zero does not equal one.

---

## Use symbols when user research supports their use

Only use mathematical symbols in general content if user research shows they are appropriate for your users and for the type of content.

Complicated mathematical relationships are difficult to express in words and are best written using symbols. These are more likely to appear in technical content, but user research might show it is appropriate to reproduce them in general content.

If so, follow this guidance to write and space mathematical symbols correctly.

---

### Use code for symbols, not punctuation

Always use the correct code for mathematical symbols:

| Symbol | Name                      | Unicode |  
|--------|---------------------------|---------|  
| +      | plus                      | U+002B  |  
| −      | minus                     | U+2212  |  
| ×      | multiplication            | U+00D7  |  
| ÷      | division                  | U+00F7  |  
| >      | greater than               | U+003E  |  
| <      | less than                  | U+003C  |  
| ≥      | greater than or equal to   | U+2265  |  
| ≤      | less than or equal to      | U+2264  |  

The +, −, ×, ÷ are **operators** (perform operations on 2 elements).  
The >, <, ≥, ≤ are **relations** (show relationships between 2 elements).

Do not use punctuation marks (such as a dash) instead of a symbol.

**Correct**  
> 8 − 0.5  [Using Unicode character for minus]

**Incorrect**  
> 8 - 0.5  [Using hyphen]

---

### Note on terminology

The Style Manual uses **symbol** rather than **sign** when referring to particular mathematical symbols (for example, “plus symbol” rather than “plus sign”).  
In mathematics, the **sign** of a number generally means whether it is positive or negative.

In non-technical writing, it is acceptable to use “sign” in terms like “plus sign”, “minus sign” etc.

---

## Don’t use a symbol or space for ratios

Ratios use a colon with **no spaces**.

**Correct**  
> 5∶1

**Incorrect**  
> 5 ∶ 1

---

## Accessibility requirements

Mathematical expressions often contain symbols and superscript. Unless coded correctly, these may be inaccessible for people who:

- have low vision  
- use screen readers  

Insert symbols and superscript with tools such as:

- Unicode  
- LaTeX  
- MathML  

Do **not** use images of symbols or superscript.  
Ensure both symbols and superscript can be enlarged without loss.

---

## Addition and positive numbers

Use the plus symbol (+) from your keyboard. Unicode: `U+002B`.

- For **addition** → use non-breaking spaces around the plus symbol  
- For **positive value** → no space after the plus symbol

**Correct**  
> 2 + 10  
> +3

**Incorrect**  
> 2+10  
> + 3

---

## Subtraction and negative numbers

Use the mathematical minus symbol (−). Unicode: `U+2212`.

- Do not use numeric keypad minus, en dash, or hyphen  
- For **subtraction** → non-breaking spaces around the minus  
- For **negative value** → no space after the minus

**Correct**  
> 12 − 4  
> −5

**Incorrect**  
> 12−4  
> − 5

---

## Division

Use either:

- Division symbol (÷) `U+00F7`  
- Division slash (∕) `U+2215`

Programming languages and Excel use `/`.

Use non-breaking spaces around ÷.  
Division slash is **unspaced** in mathematics, but consider narrow no-break spaces (`U+202F`) or thin spaces (`U+2009`) for clarity.

**Example**  
> (a + b) ÷ (x + y)  
> (a + b)∕(x + y)  
> (a + b) ∕ (x + y)  
> (a + b) ∕ (x + y)

Variables (like *x*) are italicised; do not italicise numbers or symbols.

---

## Multiplication

Use the multiplication symbol (×) `U+00D7`.  
Do not use the letter “x”.  
Dot operator (⋅) `U+22C5` is for technical use.

Use non-breaking spaces around ×.

**Write this**  
> (a + b) × (x + y)

**Not this**  
> (a + b) · (x + y)  
> (a + b) * (x + y)

---

## ‘Greater than’ and ‘less than’

- Greater than (>) `U+003E`  
- Less than (<) `U+003C`  

Use words in general content unless research shows users prefer symbols.  
Use non-breaking spaces around the symbols.

**Example**  
> 0.7 is less than 0.9  
> 0.7 < 0.9

---

## ‘Greater than or equal to’ and ‘less than or equal to’

- ≥ `U+2265`  
- ≤ `U+2264`

Do not use `>=` or `<=` in general content.

**Example**  
> Our target is greater than or equal to 90  
> x ≥ 4

---

### Don’t space when referring to a range

Expressions like `<6.74` have no space.  
Better to use words: “less than 6.74”.

---

## Use a non-breaking space to keep characters and symbols together

Insert using:

- Unicode: `U+00A0`  
- HTML: `&nbsp;`  
- Word: `Ctrl+Shift+Space`

---

## Don’t use a space if a symbol modifies a value

No space when symbol is an adjective (e.g., +3, −25).  
Non-breaking spaces when symbol acts as conjunction or verb (e.g., 6 + 6).

---

## Use the correct style for equations

- Equals symbol (=) `U+003D`  
- Non-breaking spaces around equals and operators (except division slash)  
- No space between character and superscript/subscript

**Correct**  
> 10 + 1 = 11  
> xᵃ × xᵇ = xᵃ⁺ᵇ  
> xₙ = xₙ₋₁ + xₙ₋₂

---

### Set equations as block quotations

Displayed equations are indented, centred, or left-aligned.

**Example**  
> In geometrical optics, Newton’s formula for focal length is  
>   
> f = √xy  
>   
> where *f* is focal length, *x* is object distance and *y* is image distance.

---

## Codes for mathematical symbols

| Symbol | Name                      | Unicode | HTML entity | HTML decimal | HTML hex | Word subset |
|--------|---------------------------|---------|-------------|--------------|----------|-------------|
| +      | plus (addition)            | U+002B  | &plus;      | &#43;        | &#x2b;   | Basic Latin |
| −      | minus (subtraction)        | U+2212  | &minus;     | &#8722;      | &#x2212; | Mathematical Operators |
| ×      | multiplication             | U+00D7  | &times;     | &#215;       | &#xd7;   | Latin-1 Supplement |
| ÷      | division                   | U+00F7  | &divide;    | &#247;       | &#xf7;   | Latin-1 Supplement |
| ∕      | division slash             | U+2215  | n/a         | &#8725;      | &#x2215; | Mathematical Operators |
| =      | equals                     | U+003D  | &equals;    | &#61;        | &#x3d;   | Basic Latin |
| ≠      | not equal to               | U+2260  | &ne;        | &#8800;      | &#x2260; | Mathematical Operators |
| >      | greater than               | U+003E  | &gt;        | &#62;        | &#x3e;   | Basic Latin |
| <      | less than                  | U+003C  | &lt;        | &#60;        | &#x3c;   | Basic Latin |
| ≥      | greater than or equal to   | U+2265  | &ge;        | &#8805;      | &#x2265; | Mathematical Operators |
| ≤      | less than or equal to      | U+2264  | &le;        | &#8804;      | &#x2264; | Mathematical Operators |

---

## Release notes

The digital edition revises guidance on expressing mathematical relationships:

- Default to words; symbols allowed for complex relationships with user need  
- No en dash for minus symbol; advice on division symbols added  
- Expanded guidance on non-breaking spaces  
- Adds advice on equations and Word’s equation editor  
- Includes coding and accessibility guidance with a table of codes

The Content Guide did not cover mathematical relationships.
