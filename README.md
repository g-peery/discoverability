# discoverability
Find local commands with intelligent searching

Searches local man-pages for words similar to the query (using TF-IDF), and returns a list of what pages are found.

Be sure to run src/index.py first to create a cache of manual pages that is easier to interface with.

Then, use Make to create a short link to the searching script.

Finally, it is useable as so:

```
>disc example search query
npm-search (1)
npm-help-search (1)
host (1)
mdig (1)
fc-query (1)
systemd-path (1)
btrfs-inspect-internal (8)
resolv.conf (5)
nslookup (1)
systemd-ask-password (1)
dig (1)
whereis (1)
delv (1)
uri (7)
resolver (3)
resolvectl (1)
find (1)
systemd-hwdb (8)
dhcp-eval (5)
```
