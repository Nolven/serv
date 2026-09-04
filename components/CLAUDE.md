# The one rule
 
`components/<name>/` is a **read-only source of defaults**. Nothing in it is
ever edited, templated in place, or written to during a run. All output goes to
`build/<name>/`.