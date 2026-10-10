<!--
The hand-written part of the next release: what is new, why it matters, and
what an upgrade needs. It is placed above the list of commits in the GitHub
release and in CHANGELOG.md.

Write below this comment. Use "###" for headings -- "##" is the level of the
version itself. A release with nothing written here is refused. A beta from
dev keeps the text; the stable release from main empties this file again.

Nothing inside an HTML comment is published.
-->

### Channel order on the card

The card can now show its channels in an order of your choosing. In the visual editor the
selected channels are dragged into place, and the new `sort` option orders the list on its
own: by name, with the most unread messages first, or with the most recent message first.
That also works for a card showing all channels, which so far always listed them in the
order they were created in.

Nothing changes for existing cards: without `sort` the order stays as it was.

### Releases

Releases are now produced by the release workflow all stefgo projects share. A version can
be tried as a beta before it is released, and every release is described here by hand, above
the list of commits.
