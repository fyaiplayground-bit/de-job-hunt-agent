// One-page resume template, version 1 (decision #36).
//
// The content arrives as JSON in sys.inputs.data, built by agents/render_resume.py from a
// resume.md. Values are shown as plain strings, so nothing in the content is read as markup.
//
// ATS rules this layout keeps: one column, standard headings, contact details in the body,
// nothing in headers or footers, no tables or images. Ligatures and hyphenation are off so
// every word stays whole in the text layer. `date: none` keeps the PDF byte-identical for the
// same input.

#let d = json(bytes(sys.inputs.data))

#set document(title: d.name + " - Resume", author: d.name, date: none)
#set page(paper: "us-letter", margin: (x: 0.7in, y: 0.6in), header: none, footer: none)
#set text(font: "Liberation Sans", size: 10.5pt, lang: "en", ligatures: false, hyphenate: false)
#set par(leading: 0.55em, spacing: 0.6em, justify: false)
#set list(marker: [•], indent: 0pt, body-indent: 0.5em, spacing: 0.55em)

#show heading.where(level: 1): it => block(below: 0.45em, text(size: 20pt, weight: "bold", it.body))
#show heading.where(level: 2): it => block(above: 1.1em, below: 0.55em, width: 100%, stroke: (bottom: 0.6pt), inset: (bottom: 3pt), text(size: 11.5pt, weight: "bold", it.body))

// One job, project or degree. Title and dates stay left, where the eye scans.
#let entry(e) = block(above: 0.9em, below: 0.5em, {
  text(weight: "bold", e.title)
  if e.detail != "" { [#e.detail] }
  if e.dates != "" {
    linebreak()
    text(style: "italic", e.dates)
  }
  if e.bullets.len() > 0 {
    v(0.1em)
    list(..e.bullets.map(b => [#b]))
  }
})

#heading(level: 1, d.name)
#if d.headline != "" {
  block(below: 0.45em, text(size: 12pt, d.headline))
}
#d.contact

#for s in d.sections {
  heading(level: 2, s.heading)
  if s.text != "" {
    par(s.text)
  }
  for e in s.entries {
    entry(e)
  }
}
