# Notes from Tuesday's handoff

Mara called at 8:12, before I'd found coffee. The import had stopped again. Same ugly
CSV, different row this time.

I asked Dr. Patel to send the file as-is (not a screenshot, please). He did, plus three
messages explaining why the header was probably fine. It wasn't. There was a tab tucked
inside one field and, for reasons nobody remembers, dates from 1998 mixed with dates from
last Thursday.

We tried the boring fix first. Strip the stray tab. Parse the old dates separately. That
got us through 612 rows.

Then row 613 arrived.

I laughed, which didn't help, and went outside for five minutes. There's a bakery behind
the customer office; the guy there has started setting aside the sesame rolls because he
knows our migration week routine. Anyway, when I came back, Jo had noticed the real bug:
an exporter was changing its delimiter whenever an address contained a comma.

The patch is small. The decision around it isn't — we can keep accepting the bad export,
or ask the customer to change a process they've used for nine years. For tomorrow's test,
I'm keeping the tolerant parser and logging every repaired row. Jo will bring the counts
to the 10 a.m. call.

One loose end: nobody owns the exporter. Sam thinks Finance does. Finance says it belongs
to Operations. I'll ask both, then write down the answer somewhere we might actually find
it next month.
