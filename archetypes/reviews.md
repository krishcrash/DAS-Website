---
# ---- Editorial (hand-written, or migrated from WordPress) -------------------
title: "{{ replace .File.ContentBaseName "-" " " | title }}"
# The screening date. Drives ordering: the home page features the newest.
date: {{ .Date }}
# Must match the `movie` column in master-data/ratings_by_metric.csv exactly,
# so this page can be joined to its scores. Defaults to the title.
score_key: "{{ replace .File.ContentBaseName "-" " " | title }}"
director: ""
year:
nominator: ""           # user_code from master-data/config_users.csv, e.g. KS
nominations:            # the shortlist that month; winner = the film screened
  - { film: "", votes: 0 }
  - { film: "", votes: 0, winner: true }
poster: "images/posters/{{ .File.ContentBaseName }}.jpg"   # any aspect ratio
banner: ""              # optional wide still for the hero; falls back to poster
poster_focus: ""        # optional crop anchor, e.g. "70% 30%" (x y) if the subject is off-centre
aliases: []             # legacy URLs, e.g. /midsommar/
draft: true
# ---- Scores ------------------------------------------------------------------
# Not stored here. Rank, category averages, consensus, The Fan / The Cynic /
# The Specialist are computed from the score CSV on every build.
---

Plot synopsis goes here.
