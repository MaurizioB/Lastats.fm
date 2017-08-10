Lastats.fm
====

A simple viewer for last.fm listening statistics and information.  
Just run ```./lastats.py```.

Requirements:
----
- PyQt5, at least version 5.9

Known bugs
----

The retrieveing dialog window might close _before_ receiveing all tracks,
and listening data could be still received afterwards.
This issue should have been resolved, please report if any strange issue happens.

The information browser is not perfect, and its behavior is sometimes erratic and
might freeze for a couple of seconds when receiveing data, due to network activity.
