#!/usr/bin/env python3
"""Download the player class sprites (male + female pair) for first, second and transcendent classes from iRO Wiki.
  fetch_class_sprites.py            download missing sprites to images/classes/<Class>.png and write images/classes/manifest.csv
  fetch_class_sprites.py --force    download again even when the file exists
Files are saved as the wiki serves them (transparent PNG, 118x111, male and female side by side; Bard, Clown, Kagerou
show one figure and Dancer, Gypsy, Oboro the other, because those classes have one gender).
The wiki renamed four transcendent classes (Whitesmith -> Mastersmith, Creator -> Biochemist, Professor -> Scholar,
Clown -> Minstrel) and calls Star Gladiator "TaeKwon Master"; files here keep the classic names.
"""
import csv, json, os, sys, urllib.parse, urllib.request
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = f'{ROOT}/images/classes'
API = 'https://irowiki.org/w/api.php?'
UA = {'User-Agent': 'Mozilla/5.0'}

# (tier, class name, wiki file name)
CLASSES = [(t, n, w or n) for t, items in {
    'first': [('Swordman', ''), ('Mage', ''), ('Archer', ''), ('Acolyte', ''), ('Merchant', ''), ('Thief', ''),
              ('Taekwon Kid', 'TaeKwon Kid'), ('Gunslinger', ''), ('Ninja', '')],
    'second': [('Knight', ''), ('Priest', ''), ('Wizard', ''), ('Blacksmith', ''), ('Hunter', ''), ('Assassin', ''),
               ('Crusader', ''), ('Monk', ''), ('Sage', ''), ('Rogue', ''), ('Alchemist', ''), ('Bard', ''),
               ('Dancer', ''), ('Star Gladiator', 'TaeKwon Master'), ('Soul Linker', ''), ('Kagerou', ''), ('Oboro', '')],
    'trans': [('Lord Knight', ''), ('High Priest', ''), ('High Wizard', ''), ('Whitesmith', 'Mastersmith'),
              ('Sniper', ''), ('Assassin Cross', ''), ('Paladin', ''), ('Champion', ''), ('Professor', 'Scholar'),
              ('Stalker', ''), ('Creator', 'Biochemist'), ('Clown', 'Minstrel'), ('Gypsy', '')],
}.items() for n, w in items]


def die(msg): sys.exit(f'error: {msg}')


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r: return r.read()
    except OSError as e: die(f'{url}: {e}')


def main(force):
    titles = '|'.join(f'File:{w}.png' for _, _, w in CLASSES)
    info = json.loads(get(API + urllib.parse.urlencode(
        {'action': 'query', 'titles': titles, 'prop': 'imageinfo', 'iiprop': 'url|size|sha1', 'format': 'json'})))
    found = {p['title'][5:-4]: p['imageinfo'][0] for p in info['query']['pages'].values() if p.get('imageinfo')}
    os.makedirs(OUT, exist_ok=True)
    rows, missing = [], []
    for tier, name, wiki in CLASSES:
        fn = name.replace(' ', '_')
        ii = found.get(wiki)
        if not ii: missing.append(name); continue
        dst = f'{OUT}/{fn}.png'
        if force or not os.path.isfile(dst):
            open(dst, 'wb').write(get(ii['url']))
            print('downloaded', fn)
        rows.append({'tier': tier, 'class': name, 'file': f'{fn}.png', 'wiki_file': f'{wiki}.png',
                     'width': ii['width'], 'height': ii['height'], 'url': ii['url']})
    with open(f'{OUT}/manifest.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(len(rows), 'sprites in', OUT)
    if missing: die('not found on the wiki: ' + ', '.join(missing))


if __name__ == '__main__':
    a = sys.argv[1:]
    if a not in ([], ['--force']): die('usage: fetch_class_sprites.py [--force]')
    main(bool(a))
