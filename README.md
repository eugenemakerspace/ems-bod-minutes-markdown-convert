# Convert Google docs markdown export to EMS wiki-ready markdown

We're taking minutes and notes in a google doc to facilitate real-time collaborative editing. But we need a durable output in a consistent format for reference and archival purposes. `minutes.py` takes the google docs markdown export from a given template and format and does some light transforms on it notably: 

`@action Name to do something or other` gets converted to `{{action|Name|do something or other}}` which matches a template or macro we  have installed in our wikimedia instance

Same deal with `@motion`, `@Motion: Name, Thing we voted on. Seconded: Name2. Passes: approved unanimously.` gets converted to `{{Motion|Name|Thing we voted on|Name2|approved unanimously}}`

## Setup / install

`pip install mistletoe`

## How to use

From google docs, use the File > Download > Markdown (md) menu item to convert to markdown and download the output to somewhere on your filesystem, then: 

`python minutes.py path/to/downloaded-markdown.md > wiki-ready.md`

The contents of the output (e.g. wiki-ready.md) just needs to get pasted into the edit field in the wiki. We use a filenaming convention of `EMSBoDMeetingMinutes{MM}{DD}{YY}`, e.g. EMSBoDMeetingMinutes041525 for these documents in the wiki. 
