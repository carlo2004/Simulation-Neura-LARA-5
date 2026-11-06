"""Development tasks over one to five equal cubes, with trusted goal definitions."""
from copy import deepcopy
import random

from stacklab.config import COLORS, Config

CUBE_SIZE_M = .04
STARTS = {'red': (.32, -.16), 'blue': (.50, -.12), 'green': (.31, -.01),
          'yellow': (.52, .01), 'purple': (.43, -.22)}


def cube(name, xy, color=None):
    return dict(name=name, shape='cube', xy_m=list(xy), size_m=CUBE_SIZE_M,
                color=COLORS[color or name])


def cubes(*names):
    return [cube(name, STARTS[name]) for name in names]


def task(group, instruction, objects, goal, *, hover=.24, jitter=.006):
    return dict(group=group, instruction=instruction, objects=objects, goal=goal,
                hover_z_m=hover, random_jitter_m=jitter)


def slot(x, y, z=.02, **constraints):
    return dict(centre_m=[x, y, z], **constraints)


JOINT_TARGET = [-.15, .05, 1.65, .04, 1.43, 2.82]
SORT_CUBES = [cube('red_a', (.31, -.18), 'red'), cube('red_b', (.50, -.18), 'red'),
              cube('blue_a', (.31, -.05), 'blue'), cube('blue_b', (.50, -.05), 'blue')]

TASKS = {
    'pick-up': task('single', 'Hebe den roten Würfel an. Halte seinen Mittelpunkt mindestens 10 cm über dem Tisch im Greifer.',
                    cubes('red'), dict(type='lift', source='red', min_z_m=.10)),
    'drop': task('single', 'Hebe den roten Würfel auf und lasse ihn aus mindestens 12 cm Mittelpunktshöhe bei x=0.45 m, y=0.13 m fallen. Ziehe den Greifer danach zurück.',
                 cubes('red'), dict(type='drop', source='red', target_xy_m=[.45, .13], release_min_z_m=.12, tolerance_m=.03)),
    'place-absolute': task('single', 'Lege den roten Würfel mit seinem Mittelpunkt bei x=0.45 m, y=0.12 m auf dem Tisch ab.',
                           cubes('red'), dict(type='place', source='red', target_xy_m=[.45, .12])),
    'place-relative': task('single', 'Versetze den roten Würfel auf dem Tisch um 9 cm nach rechts (+X) gegenüber seiner Startposition. Behalte seine Y-Koordinate bei.',
                           cubes('red'), dict(type='place', source='red', delta_xy_m=[.09, 0])),
    'move-joints': task('single', f'Fahre die sechs Armgelenke in Radiant auf {JOINT_TARGET}.',
                        cubes('red'), dict(type='joints', target_rad=JOINT_TARGET)),
    'rotate-cube': task('single', 'Drehe den roten Würfel um +45 Grad um die Welt-Z-Achse und lege ihn wieder am Startplatz ab.',
                        cubes('red'), dict(type='place', source='red', yaw_delta_deg=45)),
    'stack-ordered': task('multi', 'Baue einen Turm mit Blau unten, Rot in der Mitte und Grün oben. Gib die Würfel frei und ziehe den Greifer zurück.',
                          cubes('red', 'blue', 'green'), dict(type='tower', objects=['blue', 'red', 'green'], ordered=True), hover=.31),
    'stack-unordered': task('multi', 'Stapele alle fünf Würfel zu einem einzigen Turm. Die Farbreihenfolge ist beliebig. Ziehe den Greifer danach zurück.',
                            cubes('red', 'blue', 'green', 'yellow', 'purple'),
                            dict(type='tower', objects=list(STARTS), ordered=False), hover=.32),
    'shape-line': task('multi', 'Ordne die drei Würfel in einer Linie entlang X an. Ihre Mittelpunkte sollen bei x=0.30, 0.40 und 0.50 m liegen, alle bei y=0.16 m auf dem Tisch. Die Farbreihenfolge ist beliebig.',
                       cubes('red', 'blue', 'green'),
                       dict(type='layout', slots=[slot(.30, .16), slot(.40, .16), slot(.50, .16)])),
    'shape-l': task('multi', 'Lege die drei Würfel als L auf den Tisch. Die Mittelpunkte (x, y) in Metern sollen (0.34, 0.10), (0.44, 0.10) und (0.34, 0.20) sein. Die Farben sind beliebig.',
                    cubes('red', 'blue', 'green'),
                    dict(type='layout', slots=[slot(.34, .10), slot(.44, .10), slot(.34, .20)])),
    'pyramid': task('multi', 'Baue eine Pyramide aus drei Würfeln. Lege Blau bei (0.38, 0.12) m und Rot bei (0.424, 0.12) m auf den Tisch. Lege Grün mittig über beide, sodass beide unteren Würfel Grün tragen. Ziehe den Greifer zurück.',
                    cubes('red', 'blue', 'green'),
                    dict(type='layout', slots=[slot(.38, .12, name='blue'), slot(.424, .12, name='red'),
                                              slot(.402, .12, .06, name='green', supports=['blue', 'red'])])),
    'sort-colour': task('multi', 'Sortiere nach Farbe. Beide roten Würfel sollen bei x=0.31 m liegen, beide blauen bei x=0.49 m. Jede Farbe belegt die zwei Tischplätze y=0.10 m und y=0.20 m.',
                        SORT_CUBES, dict(type='layout', slots=[slot(x, y, color=color)
                            for x, color in ((.31, 'red'), (.49, 'blue')) for y in (.10, .20)])),
    'move-around-obstacle': task('multi', 'Bringe den roten Würfel auf dem Tisch nach x=0.50 m, y=0.15 m. Lass den gelben Hinderniswürfel während der gesamten Bewegung an seinem Platz.',
                                 [cube('red', (.31, -.16)), cube('obstacle', (.405, -.005), 'yellow')],
                                 dict(type='place', source='red', target_xy_m=[.50, .15], protect=['obstacle'])),
    'already-solved': task('edge', 'Lege den roten Würfel bei x=0.32 m, y=-0.16 m auf dem Tisch ab.',
                           cubes('red'), dict(type='response', intent='no_op', source='red', target_xy_m=[.32, -.16]), jitter=0),
    'missing-object': task('edge', 'Staple den roten Würfel auf den lila Würfel.',
                           cubes('red', 'blue'), dict(type='response', intent='cannot_execute')),
    'unrelated': task('edge', 'Schalte das Licht in der Küche aus.',
                       cubes('red'), dict(type='response', intent='cannot_execute')),
    'ambiguous-colour': task('edge', 'Staple den roten Würfel auf den blauen Würfel.',
                            [*SORT_CUBES[:2], cube('blue', (.40, .12))], dict(type='response', intent='clarify')),
}

for name, direction, xyz, yaw in (
    ('top', 'von oben', [.40, -.08, .29], 0),
    ('left', 'von links', [.40, -.12, .26], 0),
    ('right', 'von rechts', [.36, -.14, .24], 0),
    ('bottom', 'von unten', [.47, -.24, .37], 90),
):
    yaw_text = f' Drehe diese Ausrichtung um {yaw} Grad um Welt-Z.' if yaw else ''
    TASKS['orient-'+name] = task('single', f'Fahre den Greifer nach {xyz} m und richte ihn {direction} aus.'+yaw_text,
                               cubes('red'), dict(type='pose', target_m=xyz, orientation=name, yaw_deg=yaw), jitter=0)


def task_definition(name, seed):
    definition = deepcopy(TASKS[name])
    goal = definition['goal']
    config = Config(seed=seed, objects=definition['objects'], hover_z_m=definition['hover_z_m'],
                    random_jitter_m=definition['random_jitter_m'])
    if name == 'move-around-obstacle':
        origin = config.objects[0]['xy_m']
        fraction = random.Random(seed).uniform(.43, .57)
        config.objects[1]['xy_m'] = [a+fraction*(b-a) for a, b in zip(origin, goal['target_xy_m'])]
    return dict(name=name, group=definition['group'], instruction=definition['instruction'],
                source=goal.get('source'), target=goal.get('target'), scene_seed=seed,
                config=config.to_dict(), initial_object_positions=config.scene(), goal=goal)
