Lastats.fm
====

A simple viewer for last.fm listening statistics and information.  
Just run ```./lastats.py```.

Known bugs
----

The retrieveing dialog window might close _before_ receiveing all tracks,
and listening data could be still received afterwards. This happen expecially
when trying to retrieve large amount of tracks (>1000) and the background
receiveing process might still work well beyond the dialog has been closed.
Keep this in mind, when trying to download your whole listening history.

The information browser is not perfect, and its behavior is sometimes erratic and
might freeze for a couple of seconds when receiveing data, due to network activity.
