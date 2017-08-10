#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import sys, csv, os, pickle, zlib, re
from collections import OrderedDict, namedtuple
from bisect import bisect_left, bisect_right
from funcs import *
from threading import Event
from Queue import Queue
from PyQt5 import QtCore, QtGui, QtWidgets, QtNetwork, uic
import pylast

lastfmHttpRegex = re.compile(r'<a href=[\"\']http[s]*:\/\/(?:www\.)*last.fm')
lastfmError = namedtuple('lastfmError', 'type details func error')
lastfmError.__new__.__defaults__ = (None, )
dateRange = namedtuple('dateRange', 'first, last')
OBJECT_ROLE = QtCore.Qt.UserRole + 1
COUNT_ROLE = OBJECT_ROLE + 1
DATE_ROLE = COUNT_ROLE + 1
PAGE, TITLE, ALBUM, ARTIST, TRACK_INFO, TRACK_INFO_EXT, ARTIST_INFO, ARTIST_INFO_EXT, ALBUM_INFO, \
ALBUM_INFO_EXT, ALBUM_TRACKS, CORRECTION, TOP_ALBUMS, TOP_ALBUM_IMAGE, SIMILAR_ARTISTS, \
TOP_TRACKS, ARTIST_TAGS, ALBUM_TAGS, TRACK_TAGS, TOP_ARTISTS = xrange(20)
COVER_IMAGE, ARTIST_IMAGE = 100, 200
NODATA = 256
KEY = '757e2ce9202546d60bb73f4d8f8e07c0'
SECRET = 'f138a6352eeef0d5398c7b6a387c0b7a'

EXTERNAL_IMG = '<img src="file://external.png" title="Read more on Last.fm">'

def print_dict(d, tab=''):
    indent = tab + '    '
    for k, v in d.items():
        print '{}{}'.format(tab, str(k))
        if isinstance(v, dict):
            print_dict(v, indent)
        elif isinstance(v, (list, tuple)):
            print v
        else:
            if isinstance(v, (str, unicode)):
                out = v
            elif isinstance(v, int):
                out = str(v)
            elif isinstance(v, pylast.Artist):
                out = v.name
            else:
                out = v.title
            try:
                print '{}{}'.format(indent, out[:16])
            except:
                print out.__name__, type(v)


def _lastfm_replace(txt):
    return txt.replace('Read more on Last.fm', EXTERNAL_IMG).replace(
            'User-contributed text is available under the Creative Commons By-SA License; additional terms may apply.', '')

def _object_url(obj):
    return '<a href="{url}">{img}</a>'.format(url=obj.get_url(), img=EXTERNAL_IMG)

class NotFound(object):
    def __init__(self, object, *args):
        self.object = object
        self.args = args
        self.page_title = 'Not found'

    def str(self, *args):
        return '{obj_type} "{obj}" not found on last.fm.'.format(obj_type=self.object.__class__.__name__, obj=self.object)

class _BaseHtml(object):
    re_sub = '[ \'\"()\[\]\{\}\-\&\/\.]+'
    def __init__(self, object, *args):
        self.object = object
        self.args = args
        self.page_title = ''
        self.cover = self.correction = self._track_info = self._track_info_ext = self._track_info_link = \
            self.artist_image = self.artist_info = self.album = self._album = self.album_info = \
            self.similar_artists = self.track_tags = self.album_tags = self.artist_tags = \
            self.top_artists = self._top_albums = ''
        self.album_tracklist = None
        self.top_tracklist = []
        self.top_tracklist_albums = []
        self.func_dict = {
            COVER_IMAGE: self.setCover, 
            CORRECTION: self.setCorrection, 
            TRACK_INFO: self.setTrackInfo, 
            TRACK_INFO_EXT: self.setTrackInfoExt, 
            TRACK_TAGS: lambda tags: self.setTags(tags, TRACK_TAGS), 
            ARTIST_IMAGE: self.setArtistImage, 
            ARTIST_INFO: self.setArtistInfo, 
            ARTIST_INFO_EXT: self.setArtistInfo, 
            ARTIST_TAGS: lambda tags: self.setTags(tags, ARTIST_TAGS), 
            ALBUM_INFO: self.setAlbumInfo, 
            ALBUM_TRACKS: self.setAlbumTracks, 
            ALBUM_TAGS: lambda tags: self.setTags(tags, ALBUM_TAGS), 
            SIMILAR_ARTISTS: self.setSimilarArtists, 
            }

    @property
    def top_albums(self):
        return self._top_albums

    @property
    def top_tracks(self):
        if not self.top_tracklist:
            return ''
        try:
            return self._top_tracks_html
        except:
            self._top_tracks_html = self.getTopTracks(self.top_tracklist)
            return self._top_tracks_html

    @property
    def album_tracks(self):
        if not self.album_tracklist:
            return ''
        try:
            return self._album_tracks_html
        except:
            self._album_tracks_html = self.getAlbumTracks(self.album_tracklist)
            return self._album_tracks_html
        return ''

    @property
    def artist(self):
        return u'<a href="lastfm://artist/{_artist}">{artist}</a>'.format(_artist=urlEncode(self._artist), artist=tagReplace(self._artist))

    def track_info(self, full=False):
        if not full or not self._track_info_ext:
            if not self._track_info:
                return ''
            html = u'<br/>' + self._track_info
            if self._track_info_ext and self._track_info_ext != self._track_info:
                html += u' <a href="#track_info_expand" title="Show more" style="text-decoration: underline;">read more...</a> '
            html += u' ' + self._track_info_link
            return html
        return u'<br/>' + self._track_info_ext + ' ' + self._track_info_link

    def setTags(self, tag_list, info_type):
        tags = [u'<a href="lastfm://tag/{_tag}">#{tag}</a>'.format(_tag=urlEncode(tag.name), tag=tagReplace(tag.name)) for tag in tag_list]
        tag_html = u'<br/>Tags: {}'.format(u' · '.join(tags))
        if info_type == ARTIST_TAGS:
            self.artist_tags = tag_html
        elif info_type == TRACK_TAGS:
            self.track_tags = tag_html
        else:
            self.album_tags = tag_html

    def setSimilarArtists(self, artists):
        artists = [u'<li><a href="lastfm://artist/{_artist}">{artist}</a></li>'.format(_artist=urlEncode(a.name), artist=tagReplace(a.name)) for a in artists]
        self.similar_artists = u'<br/><h2>Similar artists</h2><ul>{}</ul>'.format(u''.join(artists))

    def setData(self, data, info_type, *args):
        try:
            self.func_dict[info_type](data if not args else data, *args)
        except:
            pass

    def setCorrection(self, name):
        self.correction = u'<font color="lightGray">scrobbled as "{}"</font><br/>'.format(self.title)
        self.title = unicode(name)

    def setCover(self, name, *args):
        self.cover = '<table border=1><tr><td><img src="file://{}"></td></tr></table>'.format(name)

    def setTrackInfo(self, info):
        if lastfmHttpRegex.findall(info):
            link_pos = tuple(lastfmHttpRegex.finditer(info))[-1].start()
            link = info[link_pos:]
            info = info[:link_pos].rstrip(' \n')
            if link.endswith('.'):
                link = link[:-1]
            self._track_info_link = _lastfm_replace(link)
        else:
            info = _lastfm_replace(info)
        self._track_info = info.replace(u'\n', '<br/>')

    def setTrackInfoExt(self, info):
        if lastfmHttpRegex.findall(info):
            link_pos = tuple(lastfmHttpRegex.finditer(info))[-1].start()
            link = info[link_pos:]
            info = info[:link_pos]
            if link.endswith('.'):
                link = link[:-1]
        else:
            info = _lastfm_replace(info)
        self._track_info_ext = info.rstrip(' \n').replace(u'\n', '<br/>')

    def setArtistImage(self, name, *args):
        self.artist_image = '<table class="artist_image"><tr><td><img src="file://{}"></td></tr></table>'.format(name)

    def setArtistInfo(self, info):
        self.artist_info = info.replace(u'\n', '<br/>').replace('Read more on Last.fm', EXTERNAL_IMG).replace(
            'User-contributed text is available under the Creative Commons By-SA License; additional terms may apply.', '')

    def setAlbumInfo(self, info):
        self.album_info = info.replace(u'\n', '<br/>').replace('Read more on Last.fm', EXTERNAL_IMG).replace(
            'User-contributed text is available under the Creative Commons By-SA License; additional terms may apply.', '')

    def setTopTracks(self, tracks):
        self.top_tracklist = tracks

    def setTopTrackAlbum(self, track):
        self.top_tracklist_albums.append(track)
        if len(self.top_tracklist_albums) == len(self.top_tracklist):
            try:
                del self._top_tracks_html
            except:
                pass

    def getTopTracks(self):
        return ''

    def setAlbumTracks(self, tracks):
        self.album_tracklist = tracks

    def getAlbumTracks(self, tracks):
        if self._album:
            _album = urlEncode(self._album)
        else:
            _album = '_'
        if self._artist:
            _artist = urlEncode(self._artist)
        else:
            _artist = '_'
        tracks = [u'<a href="lastfm://track/{_artist}/{_album}/{_title}">{title}</a>'.format(
            _artist=_artist, 
            _album=_album, 
            _title=urlEncode(track),
            title=tagReplace(track), 
            ) for track in tracks]
        try:
            current = tracks.index(self.title)
            tracks[current] = u'<b>{}</b>'.format(tracks[current])
        except:
            title_clean = re.sub(self.re_sub, ' ', self.title.lower())
            lowers = [re.sub(self.re_sub, ' ', t.lower()) for t in tracks]
            for i, track in enumerate(lowers):
                if title_clean in track:
                    tracks[i] = u'<b>{}</b>'.format(tracks[i])
                    break
                
        return u'<ol>{}</ol>'.format(u''.join(u'<li>&zwnj;{}</li>'.format(t) for t in tracks))
#        self.album_tracks = info.replace(u'\n', u'<br/>').replace(u'>{}<'.format(self.title), '><b>{}</b><'.format(self.title)).replace('Read more on Last.fm', EXTERNAL_IMG)

    def str(self, track_info_full=False):
        return self.skeleton.format(
            title=tagReplace(self.title), 
            cover=self.cover, 
            correction=self.correction, 
            track_info=self.track_info(track_info_full), 
            track_tags=self.track_tags, 
            artist=self.artist, 
            artist_image=self.artist_image, 
            artist_info=self.artist_info, 
            artist_tags=self.artist_tags, 
            album=self.album, 
            album_info=self.album_info, 
            album_tracks=self.album_tracks, 
            album_tags=self.album_tags, 
            top_albums=self.top_albums, 
            top_artists=self.top_artists, 
            top_tracks=self.top_tracks, 
            similar_artists=self.similar_artists, 
            ) + u'<br/><br/>'


class TagHtml(_BaseHtml):
    def __init__(self, tag, count=None):
        super(TagHtml, self).__init__(tag, count)
        self.title = unicode(tag.name)
        self._artist = ''
        self.page_title = 'Tag: #{}'.format(tagReplace(tag.name))
        self.skeleton = u'''
            <h1>Tag #{title}</h1>
            {top_artists}
            {top_tracks}
            {top_albums}
            '''
        func_dict = {
            TOP_ARTISTS: self.setTopArtists, 
            TOP_ALBUMS: self.setTopAlbums, 
            TOP_ALBUM_IMAGE: self.setTopAlbumImage, 
            TOP_TRACKS: self.setTopTracks
            }
        self.func_dict.update(func_dict)
        self.top_albums_data = OrderedDict()

    def setTopArtists(self, artists):
        artists = [u'<li><a href="lastfm://artist/{_artist}">{artist}</a></li>'.format(_artist=urlEncode(a.name), artist=tagReplace(a.name)) for a in artists]
        self.top_artists = u'<br/><h2>Top artists</h2><ul>{}</ul>'.format(u''.join(artists))

    @property
    def top_albums(self):
        if not self.top_albums_data:
            return ''
        html = '<h2>Top albums</h2><table width="100%" class="top_albums_container"><tr><td>'
        for album, (title, artist, image) in self.top_albums_data.items():
            short = title[:12] + u'…' if len(title) > 16 else title
            html += u'''<a href="lastfm://album/{_artist}/{_title}" title="{artist} - {title}"><table class="top_albums" style="float: left;">
                            <tr><td align=center><img src="file://{image}"></td></tr>
                            <tr><td align=center style="padding-bottom: 2px">{short}</td></tr>
                        </table></a> '''.format(
                _artist=urlEncode(artist), 
                artist=tagReplace(artist), 
                _title = urlEncode(title), 
                title=tagReplace(title), 
                short=tagReplace(short), 
                image=image if image else 'nocover_medium.png'
                )
        html += '</td></tr></table>'
        return html

    def setTopAlbums(self, albums):
        self.top_albums_data = OrderedDict()
        for album in albums:
            self.top_albums_data[album] = [album.title, album.artist.name, '']

    def setTopAlbumImage(self, name, album):
        self.top_albums_data[album][2] = name

    def getTopTracks(self, tracks):
        top_tracks = []
        for track in tracks:
            title = track.title
            artist = track.artist.name
            if track in self.top_tracklist_albums:
                _album = urlEncode(track.album_object.title if track.album_object else '_')
            else:
                _album = '_'
            html = u'<li><a href="lastfm://track/{_artist}/{_album}/{_title}">{artist} - {title}</a></li>'.format(
                _artist=urlEncode(artist), 
                _album=_album, 
                _title=urlEncode(title), 
                artist=tagReplace(artist), 
                title=tagReplace(title)
                )
            top_tracks.append(html)
        return u'<h2>Top tracks</h2><ul>{}</ul>'.format(u''.join(top_tracks))


class TrackHtml(_BaseHtml):
    def __init__(self, track, count=None):
        super(TrackHtml, self).__init__(track, count)
        self._track = track
        self.title = unicode(track.title)
        self._artist = unicode(track.artist)
        self.page_title = u'{}: {}'.format(tagReplace(self._artist), tagReplace(self.title))
        self.skeleton = u'''
            {cover}
            <h1>{title} <track_url></h1>
            {correction}<count>
            {track_tags}
            {track_info}
            <h2>{artist} <artist_url></h2><br/>
            {artist_image}{artist_info}
            {album}
            {album_info}
            {album_tracks}
            '''.replace(
                '<count>', 'Played {} times<br/><br/>'.format(count) if count is not None else ''
                ).replace(
                '<track_url>', _object_url(track)
                ).replace(
                '<artist_url>', _object_url(track.artist)
                )
        self.func_dict.update({ALBUM: self.setAlbum})

    def setAlbum(self, name):
        self.args = (name, ) + self.args
        self._album = unicode(name)
        self.album = u'<h2><a href="lastfm://album/{_artist}/{_title}">{title} {album_url}</a></h2>'.format(
            _artist=urlEncode(self._artist), 
            _title=urlEncode(name), 
            title=tagReplace(name), 
            album_url=_object_url(self._track.album_object)
            )


class ArtistHtml(_BaseHtml):
    def __init__(self, artist, count=None):
        super(ArtistHtml, self).__init__(artist, count)
        self._artist = unicode(artist.name)
        self.title = ''
        self.page_title = tagReplace(self._artist)
        self.skeleton = u'''
            {cover}
            <h1>{artist} <artist_url></h1>
            {correction}<count>
            {artist_tags}
            <ul><li><a href="#top_tracks">Top tracks</a></li>
            <li><a href="#top_albums">Top albums</a></li>
            <li><a href="#similar_artists">Similar artists</a></li></ul>
            {artist_info}
            <a name="top_tracks"/>{top_tracks}
            <a name="top_albums"/>{top_albums}
            <a name="similar_artists"/>{similar_artists}
            '''.replace(
                '<count>', 'Played {} times<br/><br/>'.format(count) if count is not None else ''
                ).replace(
                '<artist_url>', _object_url(artist)
                )
        func_dict = {
            ARTIST_IMAGE: self.setCover, 
            TOP_ALBUMS: self.setTopAlbums, 
            TOP_ALBUM_IMAGE: self.setTopAlbumImage, 
            TOP_TRACKS: self.setTopTracks
            }
        self.func_dict.update(func_dict)
        self.setArtistImage = self.setCover
        self.top_albums_data = OrderedDict()

    def setArtistImage(self, name):
        self.artist_image = '<img src="file://{}" style="float: right">'.format(name)

    @property
    def artist(self):
        return tagReplace(self._artist)

    @property
    def top_albums(self):
        if not self.top_albums_data:
            return ''
        html = '<h2>Top albums</h2><table width="100%" class="top_albums_container"><tr><td>'
        _artist = urlEncode(self._artist)
        for album, (title, image) in self.top_albums_data.items():
            short = title[:12] + u'…' if len(title) > 16 else title
            html += u'''<a href="lastfm://album/{_artist}/{_title}" title="{title}"><table class="top_albums" style="float: left;">
                            <tr><td align=center><img src="file://{image}"></td></tr>
                            <tr><td align=center style="padding-bottom: 2px">{short}</td></tr>
                        </table></a> '''.format(
                _artist=_artist, 
                _title = urlEncode(title), 
                title=tagReplace(title), 
                short=tagReplace(short), 
                image=image if image else 'nocover_medium.png'
                )
        html += '</td></tr></table>'
        return html

    def setTopAlbums(self, albums):
        self.top_albums_data = OrderedDict()
        for album in albums:
            self.top_albums_data[album] = [album.title, '']

    def setTopAlbumImage(self, name, album):
        self.top_albums_data[album][1] = name

    def getTopTracks(self, tracks):
#        top_tracks = []
#        _artist = urlEncode(self._artist)
#        for track in tracks:
#            title = track.title
#            html = u'<li><a href="lastfm://track/{_artist}/{_album}/{_title}">{title}</a></li>'.format(
#                _artist=_artist, 
#                _album=urlEncode(track.album_object.title), 
#                _title=urlEncode(title), 
#                title=tagReplace(title)
#                )
#            top_tracks.append(html)
#        self.top_tracks = u'<ul>{}</ul>'.format(u''.join(top_tracks))
        top_tracks = []
        for track in tracks:
            title = track.title
            _artist = urlEncode(self._artist)
            if track in self.top_tracklist_albums:
                _album = urlEncode(track.album_object.title if track.album_object else '_')
            else:
                _album = '_'
            html = u'<li><a href="lastfm://track/{_artist}/{_album}/{_title}">{title}</a></li>'.format(
                _artist=_artist, 
                _album=_album, 
                _title=urlEncode(title), 
                title=tagReplace(title)
                )
            top_tracks.append(html)
        return u'<h2>Top tracks</h2><ul>{}</ul>'.format(u''.join(top_tracks))


class AlbumHtml(_BaseHtml):
    def __init__(self, album, count):
        super(AlbumHtml, self).__init__(album, count)
        self.title = unicode(album.title)
        self._artist = unicode(album.artist)
        self.page_title = u'{}: {}'.format(tagReplace(self._artist), tagReplace(self.title))
        self.skeleton = u'''
            {cover}
            <h1>{title} <album_url></h1>
            {correction}<count><br/>
            {album_tags}
            {album_info}
            {album_tracks}
            <h2>{artist} <artist_url></h2><br/>
            {artist_image}{artist_info}<table>prot</table>
            '''.replace(
                '<count>', 'Played {} times<br/><br/>'.format(count) if count is not None else ''
                ).replace(
                '<album_url>', _object_url(album)
                ).replace(
                '<artist_url>', _object_url(album.artist)
                )
        self.func_dict.update({ALBUM: self.setAlbum})

    def setAlbum(self, name):
        self.args = (name, ) + self.args
        self._album = unicode(name)

    def getAlbumTracks(self, tracks):
        if self.title:
            _album = urlEncode(self.title)
        else:
            _album = '_'
        if self._artist:
            _artist = urlEncode(self._artist)
        else:
            _artist = '_'
        tracks = [u'<li>&zwnj;<a href="lastfm://track/{_artist}/{_album}/{_title}">{title}</a></li>'.format(
            _artist=_artist, 
            _album=_album, 
            _title=urlEncode(track), 
            title=tagReplace(track)
            ) for track in tracks]
        return u'<ol>{}</ol>'.format(u''.join(tracks))


class ImageDownloader(QtCore.QObject):
    imageReceived = QtCore.pyqtSignal(object)
    def __init__(self, parent, qurl):
        QtCore.QObject.__init__(self, parent)
        self.qurl = qurl
        self.netman = QtNetwork.QNetworkAccessManager(self)
        self.netman.finished.connect(self.done)
        self.request = QtNetwork.QNetworkRequest(self.qurl)
        self.netman.get(self.request)

    def done(self, reply):
        data = reply.readAll()
        image = QtGui.QImage()
        image.loadFromData(data)
        self.imageReceived.emit(image)
        self.deleteLater()


class CustomSortModel(QtGui.QStandardItemModel):
    def __init__(self, intCols, *args, **kwargs):
        QtGui.QStandardItemModel.__init__(self, *args, **kwargs)
        self.intCols = intCols
        self.sortChildren = False

    def setSortChildren(self, state):
        self.sortChildren = state

    def sort(self, column, order):
        if column in self.intCols:
            self.setSortRole(COUNT_ROLE)
        else:
            self.setSortRole(QtCore.Qt.DisplayRole)
        QtGui.QStandardItemModel.sort(self, column, order)
        if self.sortChildren:
            for parent_row in xrange(self.rowCount()):
                parent_item = self.item(parent_row, 0)
                parent_item.sortChildren(column, order)


class LastFM(QtCore.QObject):
    tracksReceived = QtCore.pyqtSignal(object, object)
    receiveFinished = QtCore.pyqtSignal()
    noUser = QtCore.pyqtSignal(str)
    userValid = QtCore.pyqtSignal(bool)
    lastfmError = QtCore.pyqtSignal(object)
    infoReceived = QtCore.pyqtSignal(object, object, int)
    albumReceivedForItem = QtCore.pyqtSignal(object, object)
    albumReceivedForTrack = QtCore.pyqtSignal(object, object)

    def __init__(self, main):
        QtCore.QObject.__init__(self)
        self.main = main
        self.defaultUser = 'MaurizioB'
        self.lastfm = pylast.LastFMNetwork(api_key=KEY, api_secret=SECRET)
        self.activateCaching()
        self.queue = Queue()
        self.retrieveStop = Event()

    def __getattr__(self, attr):
        try:
            return getattr(self.lastfm, attr)
        except (pylast.WSError, pylast.NetworkError, pylast.MalformedResponseError) as err:
            details = err.details if isinstance(err, pylast.WSError) else str(err)
            self.lastfmError.emit(lastfmError(type(err), details))
        except Exception as err:
            if err.message == '\'LastFMNetwork\' object has no attribute \'_user\'':
                return
            print 'Unknown error: {}'.format(err)

    @property
    def user(self):
        try:
            return self._user
        except:
            self._user = self.lastfm.get_user(self.defaultUser)
            return self._user

    @user.setter
    def user(self, user):
        self.queue.put((self.setUser, user))

    def activateCaching(self):
        self.cache_path = None
        temp_dirs = QtCore.QStandardPaths.standardLocations(QtCore.QStandardPaths.TempLocation)
        if temp_dirs:
            for temp_dir in temp_dirs:
                self.cache_path = temp_dir + '/lastFmCache'
                qfile = QtCore.QFile(self.cache_path)
                if not qfile.exists() or qfile.remove():
                    self.lastfm.enable_caching(self.cache_path)
                    break
            else:
                self.cache_path = None
        if not self.cache_path:
            qfile = QtCore.QFile('lastFmCache')
            if not qfile.exists() or qfile.remove():
                try:
                    self.lastfm.enable_caching('lastFmCache')
                    self.cache_path = 'lastFmCache'
                except:
                    self.cache_path = None
                    print 'Error creating the cache file, caching will not be available.'

    def enableCaching(self, state):
        if self.cache_path is None:
            return
        if state and not self.lastfm.is_caching_enabled():
            self.lastfm.enable_caching(self.cache_path)
        elif not state and self.lastfm.is_caching_enabled():
            self.lastfm.disable_caching()

    def setUser(self, user, emit=True):
        if self._user == user:
            if emit:
                self.userValid.emit(True)
            return True
        try:
            self._user = self.lastfm.get_user(user)
            self._user.get_id()
            if emit:
                self.userValid.emit(True)
            return True
        except pylast.WSError:
            if emit:
                self.userValid.emit(False)
            return False

    def start(self):
        while True:
            res = self.queue.get(True)
            if res == 'quit':
                break
            if isinstance(res, (tuple, list)) and len(res) > 1:
                func = res[0]
                args = res[1:]
            else:
                func = res
                args = []
            try:
                func(*args)
            except (pylast.WSError, pylast.NetworkError, pylast.MalformedResponseError) as err:
                details = err.details if isinstance(err, pylast.WSError) else str(err)
                self.lastfmError.emit(lastfmError(type(err), details, func.__name__, args))
            except Exception as err:
                print 'Unknown error: {}'.format(err)

    def quit(self):
        self.queue.put('quit')

    def playCount(self):
        return self.user.get_playcount()

    def getSimilar(self, obj, limit=10):
        self.queue.put(lambda: self.infoReceived.emit(obj.get_similar(limit=limit), obj, SIMILAR_ARTISTS))

    def getTopTracks(self, obj, limit=10):
        def get_tracks():
            tracks = obj.get_top_tracks(limit=limit)
            if not tracks:
                return
            tracks = [t.item for t in tracks]
            self.infoReceived.emit(tracks, obj, TOP_TRACKS)
            for track in tracks:
                #silently get albums
                track.album_object
        self.queue.put(get_tracks)

    def getTopArtists(self, tag, limit=10):
        self.queue.put(lambda: self.infoReceived.emit(tag.get_top_artists(limit=limit), tag, TOP_ARTISTS))

    def getTopAlbums(self, obj, limit=10):
        self.queue.put(lambda: self.infoReceived.emit(obj.get_top_albums(limit=limit), obj, TOP_ALBUMS))

    def getCorrection(self, obj):
        self.queue.put(lambda: self.infoReceived.emit(obj.get_correction(), obj, CORRECTION))

    def getAlbumObject(self, track):
        self.queue.put(lambda: self.albumReceivedForTrack.emit(track.album_object, track))

    def getAlbumObjectForItem(self, track, parent):
        self.queue.put(lambda: self.albumReceivedForItem.emit(track.get_album(), parent))

    def getTrackInfo(self, track):
        self.queue.put(lambda: self.infoReceived.emit(track.get_wiki_summary(), track, TRACK_INFO))
        self.queue.put(lambda: self.infoReceived.emit(track.get_wiki_content(), track, TRACK_INFO_EXT))

    def getTags(self, obj, limit=10):
        def get_tags():
            tags = obj.get_top_tags(limit=limit)
            if not tags:
                return
            self.infoReceived.emit([t.item for t in tags], obj, info_type)
        if isinstance(obj, pylast.Artist):
            info_type = ARTIST_TAGS
        elif isinstance(obj, pylast.Album):
            info_type = ALBUM_TAGS
        else:
            info_type = TRACK_TAGS
        self.queue.put(get_tags)

    def getTracks(self, album):
        def get_tracks():
            tracks = album.get_tracks()
            if not tracks:
                return
            self.infoReceived.emit([t.title for t in tracks], album, ALBUM_TRACKS)
        self.queue.put(get_tracks)

    def getAlbumInfo(self, album, full=False):
        self.queue.put(lambda full=full: self.infoReceived.emit(album.get_wiki_content() if full else album.get_wiki_summary(), album, ALBUM_INFO))

    def getBio(self, artist, full=False):
        self.queue.put(lambda full=full: self.infoReceived.emit(artist.get_bio_content() if full else artist.get_bio_summary(), artist, ARTIST_INFO_EXT if full else ARTIST_INFO))

    def getImage(self, obj, size=None):
        if isinstance(obj, pylast.Artist):
            size = size if size is not None else pylast.COVER_MEDIUM
            info_type = ARTIST_IMAGE
        else:
            size = size if size is not None else pylast.COVER_LARGE
            info_type = COVER_IMAGE
        self.queue.put(lambda: self.infoReceived.emit((obj.get_cover_image(size), size), obj, info_type))

    def getTopAlbumsImage(self, album, size=None):
        size = size if size is not None else pylast.COVER_MEDIUM
        self.queue.put(lambda: self.infoReceived.emit((album.get_cover_image(size), size), album, TOP_ALBUM_IMAGE))

    def retrieve(self, limit=None, after=None):
        self.queue.put((self.retrieveProcess, limit, after))

    def retrieveProcess(self, limit=None, after=None):
        try:
            if after is not None:
                limit = None
            #TODO crea algoritmo per approssimare numero tracce?
            for track_group, total_pages, is_final in self.user.get_recent_tracks_yield(limit=limit, page_limit=50, time_from=after):
                if self.retrieveStop.isSet():
                    self.retrieveStop.clear()
                    break
                tracks = []
                for track in track_group:
                    tracks.append((track.track, track.album, int(track.timestamp)))
                self.tracksReceived.emit(tracks, after)
                if is_final:
                    self.receiveFinished.emit()
        except pylast.WSError as err:
            self.lastfmError.emit(lastfmError(type(err), err.details))


class RetrieveMsgBox(QtWidgets.QMessageBox):
    def __init__(self, parent=None):
        QtWidgets.QMessageBox.__init__(self, parent)
        self.updating = False
        self.setWindowTitle('Retrieveing tracks')
        self.setStandardButtons(self.Cancel)
        self.setEscapeButton(self.Cancel)
        self.button(self.Cancel).clicked.connect(self.rejected)
        self.elapsedTimer = QtCore.QElapsedTimer()
        self.limit = self.current = self.previous = self.current_time = 0
        self.clock = QtCore.QTimer()
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self.updateTime)

    @property
    def baseText(self):
        if not self.updating:
            text = 'Retrieveing tracks, please wait...'
        else:
            text = 'Retrieveing latest tracks, please wait...<br/>'\
                '<b>Note</b>: cancelling this operation is <i>not yet</i> supported, and will result in uncomplete data, '\
                'which will <b>not</b> be correctly updated.<br/>'\
                'Statistics will also be unreliable too. Please, be patient.'
        return text

    def show(self, updating=False):
        self.updating = updating
        self.setText(self.baseText)
        QtWidgets.QMessageBox.show(self)
        self.elapsedTimer.start()
        self.clock.start()

    def hideEvent(self, event):
        self.clock.stop()

    def setLimit(self, limit=0):
        self.limit = limit
        self.current = 0
        self.setInformativeText('0 tracks received of {}\nRemaining time: (computing)'.format(limit if limit else '(unknown)'))

    def updateTime(self):
        if self.limit:
            if self.current_time > 1:
                self.current_time -= 1
        self.updateText()

    def updateText(self):
        if self.current == 0:
            remainder = '(computing)'
        else:
            remainder = '{}\'{:02d}"'.format(*map(int, divmod(self.current_time, 60)))
        self.setInformativeText('{} tracks received of {}\nRemaining time {}'.format(self.current, self.limit if self.limit else '(unknown)', remainder))

    def tracksAdded(self, count):
        self.current += count
        if self.current == 0:
            self.hide()
            return
        elapsed = self.elapsedTimer.elapsed() / 1000.
        single = elapsed / self.current
        if self.limit:
            self.current_time = (self.limit - self.current) * single
        self.updateText()


class History(QtCore.QObject):
    forwardAvailable = QtCore.pyqtSignal(bool)
    backwardAvailable = QtCore.pyqtSignal(bool)
    setPage = QtCore.pyqtSignal(object)
    def __init__(self, main, scrollbar):
        QtCore.QObject.__init__(self, main)
        self.main = main
        self.scrollbar = scrollbar
        self.current = -1
        self.pages = []

    def forward(self):
        if self.current + 1 >= len(self.pages):
            return
        self.current += 1
        self.backwardAvailable.emit(True if self.current > 0 else False)
        self.forwardAvailable.emit(True if self.current + 1 < len(self.pages) else False)
        return self.pages[self.current]

    def backward(self):
        if self.current <= 0:
            self.backwardAvailable.emit(False)
            return
        self.current -= 1
        self.backwardAvailable.emit(True if self.current > 0 else False)
        self.forwardAvailable.emit(True)
        return self.pages[self.current]

    def previousPages(self):
        if not self.pages or self.current <= 0:
            return
        prev = self.pages[:self.current]
        titles = [(i, p.page_title) for i, (p, _) in enumerate(prev)]
        return list(reversed(titles))

    def nextPages(self):
        if not self.pages or self.current + 1 >= len(self.pages):
            return
        next = self.pages[self.current + 1:]
        return list((i, p.page_title) for i, (p, _) in enumerate(next, self.current + 1))

    def newPage(self, page):
        self.current += 1
        self.pages = self.pages[:self.current]
        self.pages.append([page, 0])
        self.forwardAvailable.emit(False)
        self.backwardAvailable.emit(True if self.current > 0 else False)

    def goTo(self, id):
        self.current = id
        self.backwardAvailable.emit(True if self.current > 0 else False)
        self.forwardAvailable.emit(True if self.current + 1 < len(self.pages) else False)
        self.setPage.emit(self.pages[id])


class LaStats(QtWidgets.QMainWindow):
    def __init__(self, app):
        QtWidgets.QMainWindow.__init__(self)
        uic.loadUi(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'main.ui'), self)
        self.app = app
        self.settings = QtCore.QSettings()
        self.lastfm = LastFM(self)
        self.lastfm_thread = QtCore.QThread()
        self.lastfm.moveToThread(self.lastfm_thread)
        self.lastfm_thread.started.connect(self.lastfm.start)
        self.lastfm_thread.start()
        self.lastfm.tracksReceived.connect(self.tracksReceived)

        self.latestAdded = 0
        self.infoCache = {}
        self.history = History(self, self.infoTextArea.verticalScrollBar())
        self.historyBackBtn.setHistory(self.history, self.history.previousPages, QtWidgets.QStyle.SP_ArrowLeft)
        self.historyFwdBtn.setHistory(self.history, self.history.nextPages, QtWidgets.QStyle.SP_ArrowRight)
        self.refreshBtn.setIcon(self.refreshBtn.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))
        self.currentObject = self.currentArgs = None
        self.reset()

        self.trackCounter = QtWidgets.QLabel()
        self.artistCounter = QtWidgets.QLabel()
        self.statusBar().addPermanentWidget(self.artistCounter)
        self.statusBar().addPermanentWidget(self.trackCounter)
        self.trackModel = CustomSortModel((3, ))
        self.trackTable.setModel(self.trackModel)
        self.trackTable.setEditTriggers(self.trackTable.NoEditTriggers)
        self.trackTable.contextMenuEvent = self.tableMenuEvent
        self.trackTable.clicked.connect(self.selectTrack)
        self.trackTable.activated.connect(self.selectTrack)
        self.trackTable.activated.connect(lambda: self.tabWidget.setCurrentWidget(self.infoTab))
        self.trackTable.doubleClicked.connect(lambda: self.tabWidget.setCurrentWidget(self.infoTab))

        self.trackTreeModel = CustomSortModel((1, ), 0, 3)
        self.trackTreeModel.setSortChildren(True)
        self.trackTreeModel.setHorizontalHeaderLabels(['', 'Plays', 'Dates'])
        self.trackTreeView.setEditTriggers(self.trackTable.NoEditTriggers)
        self.trackTreeView.setModel(self.trackTreeModel)
        self.trackTreeView.clicked.connect(self.selectTree)
        self.trackTreeView.activated.connect(self.selectTree)
        self.trackTreeView.activated.connect(lambda: self.tabWidget.setCurrentWidget(self.infoTab))
        self.trackTreeView.doubleClicked.connect(lambda: self.tabWidget.setCurrentWidget(self.infoTab))

        self.overallScrollAreaWidgetContents.setContentsMargins(2, 2, 2, 2)
        self.periodScrollAreaWidgetContents.setContentsMargins(2, 2, 2, 2)
        self.userCheckTimer = QtCore.QTimer()
        self.userCheckTimer.setInterval(250)
        self.retrieveUserEdit.textChanged.connect(self.userCheckStart)
        self.userCheckTimer.setSingleShot(True)
        self.userCheckTimer.timeout.connect(lambda: setattr(self.lastfm, 'user', self.retrieveUserEdit.text()))
        self.lastfm.userValid.connect(self.userCheck)
        self.lastfm.infoReceived.connect(self.infoCacheUpdate)
        self.lastfm.albumReceivedForTrack.connect(self.albumReceivedForTrack)
        self.lastfm.albumReceivedForItem.connect(self.setAlbumObjectItem)
        self.retrieveUserEdit.returnPressed.connect(lambda: self.retrieve() if self.retrieveBtn.isEnabled() else None)
        self.retrieveBtn.clicked.connect(self.retrieve)
        self.retrieveMsgBox = RetrieveMsgBox(self)
        self.lastfm.receiveFinished.connect(self.retrieveMsgBox.hide)
        self.retrieveMsgBox.rejected.connect(self.lastfm.retrieveStop.set)
        self.saveBtn.clicked.connect(self.saveData)
        self.updateBtn.clicked.connect(self.updateTracks)
        self.loadMsgBox = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information, 'Loading...', 'Loading stored statistics, please wait.', parent=self)
        self.loadMsgBox.setStandardButtons(self.loadMsgBox.NoButton)
        self.loadMsgBox.closeEvent = lambda ev: ev.ignore()
        self.yearStatsLabel.linkActivated.connect(self.toggleYearStats)
        self.trackYearsWidget.yearSelect.connect(lambda year: (self.setYearPeriod(year), self.computePeriodStats()))

        self.topTextArea.anchorClicked.connect(self.topNavigate)
        self.periodTopTextArea.anchorClicked.connect(self.topNavigate)
        self.periodComputeBtn.clicked.connect(self.computePeriodStats)
        self.startDateEdit.dateChanged.connect(self.checkPeriods)
        self.endDateEdit.dateChanged.connect(self.checkPeriods)
        self.periodYearSpin.valueChanged.connect(self.checkPeriodYear)
#        self.periodYearBtn.clicked.connect(self.computeYearPeriod)
        self.periodMonthCombo.activated.connect(self.setMonthPeriod)
        self.periodWeekCombo.weekSelect.connect(self.setPeriodDates)
#        self.periodWeekBtn.clicked.connect(self.computeWeekPeriod)

        self.refreshBtn.clicked.connect(self.refresh)
        self.historyBackBtn.clicked.connect(lambda: self.setHistoryPage(self.history.backward()))
        self.historyFwdBtn.clicked.connect(lambda: self.setHistoryPage(self.history.forward()))
        self.history.backwardAvailable.connect(self.historyBackBtn.setEnabled)
        self.history.forwardAvailable.connect(self.historyFwdBtn.setEnabled)
        self.history.setPage.connect(self.setHistoryPage)
        self.infoTextArea.anchorClicked.connect(self.navigate)
        self.infoTextArea.mousePressEvent = self.infoTextAreaMousePressEvent
        self.infoTextArea.verticalScrollBar().valueChanged.connect(self.pageScrolled)

        self.infoTextArea.document().setDefaultStyleSheet(
            '''
            table {
                background: lightGray;
                border-color: transparent;
                }
            table.top_albums {
                background: #ffb;
                }
            table.top_albums_container {
                background: transparent;
            }
            table.artist_image {
                float: right;
                border-color: transparent;
                border-width: 2px;
                background: transparent;
            }
            h2 {
                page-break-before: always;
                margin-top: 5px;
                margin-bottom: 0px;
                }
            h1 {
                margin-top: 5px;
                margin-bottom: 0px;
                }
            a {
                text-decoration: none;
                color: #811;
                }
            ul li {
                margin-left: <indent>px;
                }
            '''.replace('<indent>', '{}'.format(20 - self.infoTextArea.document().indentWidth()))
            )
        self.infoTextArea.document().addResource(QtGui.QTextDocument.ImageResource, QtCore.QUrl('file://external.png'), QtCore.QVariant(QtGui.QImage('external.png')))
        self.infoTextArea.document().addResource(QtGui.QTextDocument.ImageResource, QtCore.QUrl('file://nocover_medium.png'), QtCore.QVariant(QtGui.QImage('nocover_medium.png')))

        self.shown = False
        self.currentUser = self.settings.value('user', '')
        if self.currentUser:
            self.retrieveUserEdit.setText(self.currentUser)
#        self.retrieveUserEdit.setText('MaurizioB')
        self.retrieveBtn.setEnabled(False)
        self.setPeriodRanges()
        self.periodMonthCombo.addItems([QtCore.QDate.shortMonthName(m).title() for m in xrange(1, 13)])

    def setYearPeriod(self, year):
        if self.sender() != self.periodYearSpin:
            self.tabWidget.setCurrentWidget(self.periodStatsTab)
        self.setPeriodDates(QtCore.QDate(year, 1, 1), QtCore.QDate(year + 1, 1, 1))

#    def computeYearPeriod(self):
#        self.startDateEdit.setDate(QtCore.QDate(self.periodYearSpin.value(), 1, 1))
#        self.endDateEdit.setDate(QtCore.QDate(self.periodYearSpin.value() + 1, 1, 1))
#        self.computePeriodStats()

    def setMonthPeriod(self, month):
        start_date = QtCore.QDate(self.periodYearSpin.value(), month + 1, 1)
        self.setPeriodDates(start_date, start_date.addMonths(1))

    def setPeriodDates(self, start_date, end_date):
        def checkLimit(date):
            if date < self.periodRanges.first:
                return self.periodRanges.first
            elif date > self.periodRanges.last:
                return self.periodRanges.last
            else:
                return date

        self.startDateEdit.blockSignals(True)
        self.startDateEdit.setMaximumDate(checkLimit(end_date.addDays(-1)))
        self.startDateEdit.setDate(checkLimit(start_date))
        self.startDateEdit.blockSignals(False)

        self.endDateEdit.blockSignals(True)
        self.endDateEdit.setMinimumDate(checkLimit(start_date.addDays(1)))
        self.endDateEdit.setDate(checkLimit(end_date))
        self.endDateEdit.blockSignals(False)

#    def computeWeekPeriod(self):
#        year, week = map(int, self.periodWeekCombo.currentText().split('/'))
#        date = firstMonOfWeek(year, week)
#        self.startDateEdit.setDate(date)
#        self.endDateEdit.setDate(date.addDays(7))
#        self.computePeriodStats()

    def checkPeriodYear(self, year):
        months = [(QtCore.QDate(year, m, 1), QtCore.QDate(year, m + 1, 1)) for m in xrange(1, 12)] + [(QtCore.QDate(year, 12, 1), QtCore.QDate(year + 1, 1, 1))]
        stats_start, stats_end = self.periodRanges
        model = self.periodMonthCombo.model()
        first = None
        for index, (month_start, month_end) in enumerate(months):
            if stats_start > month_end or stats_end < month_start:
                enable = False
            else:
                enable = True
                if first is None:
                    first = index
            model.item(index).setEnabled(enable)
        if first is not None:
            self.periodMonthCombo.blockSignals(True)
            self.periodMonthCombo.setCurrentIndex(first)
            self.periodMonthCombo.blockSignals(False)
        self.setYearPeriod(year)

    def checkPeriods(self, date):
        if self.sender() == self.startDateEdit:
            self.endDateEdit.setMinimumDate(date.addDays(1))
        elif self.sender() == self.endDateEdit:
            self.startDateEdit.setMaximumDate(date.addDays(-1))

    def setPeriodRanges(self, first=None, last=None):
        if first is None:
            first = QtCore.QDate(2002, 1, 1)
            last = QtCore.QDate.currentDate().addDays(1)
        self.periodRanges = dateRange(first, last)
        self.startDateEdit.setDateRange(first, last.addDays(-1))
        self.endDateEdit.setDateRange(first.addDays(1), last)
        self.startDateEdit.setDate(first)
        self.endDateEdit.setDate(last)
        self.periodYearSpin.setRange(first.year(), last.year())
        self.periodWeekCombo.setDateRange(first, last)

    def pageScrolled(self, pos):
        if self.history.current >= 0:
            self.history.pages[self.history.current][1] = pos

    def infoTextAreaMousePressEvent(self, event):
        if event.button() == QtCore.Qt.BackButton:
            page = self.history.backward()
            if page:
                self.setHistoryPage(page)
        elif event.button() == QtCore.Qt.ForwardButton:
            page = self.history.forward()
            if page:
                self.setHistoryPage(page)
        else:
            QtWidgets.QTextBrowser.mousePressEvent(self.infoTextArea, event)

    def toggleYearStats(self, link):
        if link == '#expand':
            text = '<html><head/><body><p>By years: <a href="#collapse">collapse</a></p></body></html>'
            self.trackYearsWidget.expanded = True
        else:
            text = '<html><head/><body><p>By years: <a href="#expand">expand</a></p></body></html>'
            self.trackYearsWidget.expanded = False
        self.yearStatsLabel.setText(text)

    def showEvent(self, event):
        if self.shown: return
        self.shown = True
        if QtCore.QFile('stats.gz').exists():
            QtCore.QTimer.singleShot(50, self.loadMsgBox.show)
        QtCore.QTimer.singleShot(100, self.loadData)
        self.periodScrollArea.setMinimumWidth(
            self.periodScrollAreaWidgetContents.width() + 
            self.periodScrollAreaWidgetContents.getContentsMargins()[0] + 
            self.periodScrollAreaWidgetContents.getContentsMargins()[2] + 
            self.periodScrollArea.getContentsMargins()[0] + 
            self.periodScrollArea.getContentsMargins()[2] + 
            (self.periodScrollArea.lineWidth() + self.periodScrollArea.midLineWidth() + self.periodScrollArea.frameWidth()) * 2
            )

    def saveData(self):
        with open('stats.gz', 'wb') as stream:
            try:
                self.lastfm.enableCaching(False)
                stream.write(zlib.compress(pickle.dumps(self.track_data), 9))
                self.lastfm.enableCaching(True)
                self.saveBtn.setEnabled(False)
            except Exception as e:
                print 'Error saving stats: {}'.format(e)

    def loadData(self):
        try:
            with open('stats.gz', 'rb') as stream:
                zdata = zlib.decompress(stream.read())
                data = pickle.loads(zdata)
            self.tracksReceived(data, enable_save=False)
        except Exception as e:
            print e
        self.loadMsgBox.hide()

    def selectTrack(self, index):
        track_item = self.trackModel.item(index.row(), 0)
        track_object = track_item.data(OBJECT_ROLE)
        album_title = self.trackModel.item(index.row(), 2).text()
        count = self.trackModel.item(index.row(), 3).text()
        self.showTrack(track_object, album_title, count)

    def selectTree(self, index):
        obj_index = self.trackTreeModel.index(index.row(), 0, index.parent())
        item = self.trackTreeModel.itemFromIndex(obj_index)
        obj = item.data(OBJECT_ROLE)
        count = self.trackTreeModel.index(index.row(), 1, index.parent()).data()
        if isinstance(obj, pylast.Track):
            album_title = index.parent().data()
            self.showTrack(obj, album_title, count)
        elif isinstance(obj, pylast.Artist):
            self.showArtist(obj, count)
        elif isinstance(obj, pylast.Album):
            self.showAlbum(obj, count)
        else:
            if item.hasChildren():
                self.lastfm.getAlbumObjectForItem(item.child(0, 0).data(OBJECT_ROLE), item)

    def setAlbumObjectItem(self, album, item):
        if album is None:
            #TODO verificare che l'item corrisponda (vedi Will Smith)
            album = self.lastfm.get_album(item.parent().text(), item.text())
        item.setData(album, OBJECT_ROLE)
        count = self.trackTreeModel.sibling(item.row(), 1, item.index()).data()
        self.showAlbum(album, count)

    def checkPageCache(self, obj):
#        if isinstance(obj, pylast.Track) and obj.title == 'Gaeta\'s Lament':
#            for k, v in self.infoCache.items():
#                if isinstance(k, pylast.Track) and k.title == 'Gaeta\'s Lament':
#                    print 'trovato!'
#                    print 'Uguali? {}'.format(obj==k)
#                    print 'C\'è? {}'.format(obj in self.infoCache)
        try:
#            print self.infoCache[obj]
            self.infoCache[obj][PAGE]
        except:
            print 'Object "{}" not found in cache'.format(obj)
#            print_dict(self.infoCache)
        if obj in self.infoCache:
            if PAGE in self.infoCache[obj]:
                return True
            else:
                return False
        self.infoCache[obj] = {}
        return False

    def refresh(self):
        if not self.currentObject:
            return
        if isinstance(self.currentObject, pylast.Track):
            try:
                del self.infoCache[self.currentObject.album_object]
            except:
                pass
        if isinstance(self.currentObject, (pylast.Track, pylast.Album)):
            try:
                del self.infoCache[self.currentObject.artist]
            except:
                pass
        del self.infoCache[self.currentObject]
        func_dict = {
            pylast.Album: self.showAlbum, 
            pylast.Artist: self.showArtist, 
            pylast.Track: self.showTrack, 
            pylast.Tag: self.showTag, 
            }
        func_dict[type(self.currentObject)](self.currentObject, *self.currentArgs)

    def topNavigate(self, url):
        self.tabWidget.setCurrentWidget(self.infoTab)
        self.navigate(url)

    def navigate(self, url):
        if url.scheme() == 'lastfm':
            if url.host() == 'track':
                title = url.fileName(url.DecodeReserved)
                path = url.path(url.DecodeReserved)
                artist, album = map(urlDecode, path[1:-len(title)-1].split('/'))
                track = self.lastfm.get_track(artist, urlDecode(title))
                try:
                    self.showTrack(track, album)
                except:
                    self.notFound(track)
            elif url.host() == 'album':
                title = url.fileName(url.DecodeReserved)
                path = url.path(url.DecodeReserved)
                artist = urlDecode(path[1:-len(title)-1])
                album = self.lastfm.get_album(artist, urlDecode(title))
                try:
                    self.showAlbum(album)
                except:
                    self.notFound(album)
            elif url.host() == 'artist':
                artist = self.lastfm.get_artist(urlDecode(url.fileName()))
                try:
                    self.showArtist(artist)
                except:
                    self.notFound(artist)
            elif url.host() == 'tag':
                tag = self.lastfm.get_tag(urlDecode(url.fileName()))
                try:
                    self.showTag(tag)
                except:
                    self.notFound(tag)
        elif url.hasFragment() and not (url.host() and url.path()):
            if url.fragment() == 'track_info_expand':
                pos = self.infoTextArea.verticalScrollBar().value()
                self.infoTextArea.setHtml(self.infoText.str(track_info_full=True))
                self.infoTextArea.verticalScrollBar().setValue(pos)
            else:
                self.infoTextArea.scrollToAnchor(url.fragment())
        else:
            QtGui.QDesktopServices.openUrl(url)

    def notFound(self, obj):
        self.currentObject = obj
        infoText = NotFound(obj)
        self.history.newPage(infoText)
        self.infoTextArea.setHtml(infoText.str())

    def setHistoryPage(self, args):
        page, pos = args
        self.currentObject = page.object
        self.currentArgs = page.args
        self.infoText = page
        self.infoTextArea.setHtml(page.str())
        self.infoTextArea.verticalScrollBar().setValue(pos)

    def showTag(self, tag, count=None):
        if self.currentObject == tag:
            return
        self.refreshBtn.setEnabled(True)
        self.currentObject = tag
        self.currentArgs = count, 
        if self.checkPageCache(tag):
            self.history.newPage(self.infoText)
            self.infoText = self.infoCache[tag][PAGE]
            self.infoTextArea.setHtml(self.infoText.str())
            return
        self.infoText = TagHtml(tag, count)
        if tag in self.infoCache:
            top_artists = self.infoCache[tag].get(TOP_ARTISTS)
            if not top_artists:
                self.lastfm.getTopArtists(tag)
            elif top_artists is not NODATA:
                self.infoText.setTopArtists(top_artists)

            top_tracks = self.infoCache[tag].get(TOP_TRACKS)
            if not top_tracks:
                self.lastfm.getTopTracks(tag)
            elif top_tracks is not NODATA:
                self.infoText.setTopTracks(top_tracks)

            top_albums = self.infoCache[tag].get(TOP_ALBUMS)
            if not top_albums:
                self.lastfm.getTopAlbums(tag)
            elif top_albums is not NODATA:
                self.infoText.setTopAlbums(top_albums)
                for album in top_albums:
                    album_images = self.infoCache[album].get(COVER_IMAGE)
                    if album_images and album_images.get(pylast.COVER_MEDIUM):
                        self.infoText.setTopAlbumImage(album, album_images[pylast.COVER_MEDIUM])
                    elif album_images is not NODATA:
                        self.lastfm.getTopAlbumsImage(album, size=pylast.COVER_MEDIUM)
        else:
            self.lastfm.getTopArtists(tag)
            self.lastfm.getTopAlbums(tag)
            self.lastfm.getTopTracks(tag)
        self.history.newPage(self.infoText)
        self.infoTextArea.setHtml(self.infoText.str())
        self.infoCache[tag][PAGE] = self.infoText

    def showAlbum(self, album, count=None):
        if self.currentObject == album:
            return
        self.refreshBtn.setEnabled(True)
        self.currentObject = album
        self.currentArgs = count, 
        if self.checkPageCache(album):
            self.history.newPage(self.infoText)
            self.infoText = self.infoCache[album][PAGE]
            self.infoTextArea.setHtml(self.infoText.str())
            return
        artist = album.artist
        self.infoText = AlbumHtml(album, count)
        if album in self.infoCache:
            album_tracks = self.infoCache[album].get(ALBUM_TRACKS)
            if not album_tracks:
                self.lastfm.getTracks(album)
            elif album_tracks is not NODATA:
                self.infoText.setAlbumTracks(album_tracks)

            album_info = self.infoCache[album].get(ALBUM_INFO)
            if not album_info:
                self.lastfm.getAlbumInfo(album, True)
            elif album_info is not NODATA:
                self.infoText.setAlbumInfo(album_info)
#            if any((album_tracks, album_info)):
#                self.infoText.setAlbum(album.title)

            cover_images = self.infoCache[album].get(COVER_IMAGE)
            if not cover_images:
                self.lastfm.getImage(album)
            elif cover_images is not NODATA:
                cover_name = cover_images[pylast.COVER_LARGE]
                if cover_name:
                    self.infoText.setCover(cover_name)
                else:
                    self.lastfm.getImage(album)
        else:
            self.lastfm.getTracks(album)
            self.lastfm.getAlbumInfo(album, True)
            self.lastfm.getImage(album)

        if artist in self.infoCache:
            artist_info = self.infoCache[artist].get(ARTIST_INFO)
            if not artist_info:
                self.lastfm.getBio(artist)
            elif artist_info is not NODATA:
                self.infoText.setArtistInfo(artist_info)
            artist_images = self.infoCache[artist].get(ARTIST_IMAGE)
            if not artist_images:
                self.lastfm.getImage(artist)
            elif artist_images is not NODATA:
                artist_image_name = artist_images.get(pylast.COVER_MEDIUM)
                if artist_image_name:
                    self.infoText.setArtistImage(artist_image_name)
                else:
                    self.lastfm.getImage(artist, size=pylast.COVER_MEDIUM)
        else:
            self.lastfm.getBio(artist)
            self.lastfm.getImage(artist, size=pylast.COVER_MEDIUM)
        self.history.newPage(self.infoText)
        self.infoTextArea.setHtml(self.infoText.str())
        self.infoCache[album][PAGE] = self.infoText

    def showArtist(self, artist, count=None):
        if self.currentObject == artist:
            return
        self.refreshBtn.setEnabled(True)
        self.currentObject = artist
        self.currentArgs = count, 
        if self.checkPageCache(artist):
            self.history.newPage(self.infoText)
            self.infoText = self.infoCache[artist][PAGE]
            self.infoTextArea.setHtml(self.infoText.str())
            return
        self.infoText = ArtistHtml(artist, count)
        if artist in self.infoCache:
            artist_info = self.infoCache[artist].get(ARTIST_INFO_EXT)
            if not artist_info:
                self.lastfm.getBio(artist, True)
            elif artist_info is not NODATA:
                self.infoText.setArtistInfo(artist_info)

            artist_images = self.infoCache[artist].get(ARTIST_IMAGE)
            if not artist_images:
                self.lastfm.getImage(artist, size=pylast.COVER_LARGE)
            elif artist_images is not NODATA:
                artist_image_name = artist_images.get(pylast.COVER_LARGE)
                if artist_image_name:
                    self.infoText.setArtistImage(artist_image_name)
                else:
                    self.lastfm.getImage(artist, size=pylast.COVER_LARGE)

            tags = self.infoCache[artist].get(ARTIST_TAGS)
            if not tags:
                self.lastfm.getTags(artist)
            elif tags is not NODATA:
                self.infoText.setTags(tags)

            top_tracks = self.infoCache[artist].get(TOP_TRACKS)
            if not top_tracks:
                self.lastfm.getTopTracks(artist)
            elif top_tracks is not NODATA:
                self.infoText.setTopTracks(top_tracks)

            top_albums = self.infoCache[artist].get(TOP_ALBUMS)
            if not top_albums:
                self.lastfm.getTopAlbums(artist)
            elif top_albums is not NODATA:
                self.infoText.setTopAlbums(top_albums)
                for album in top_albums:
                    album_images = self.infoCache[album].get(COVER_IMAGE)
                    if album_images and album_images.get(pylast.COVER_MEDIUM):
                        self.infoText.setTopAlbumImage(album, album_images[pylast.COVER_MEDIUM])
                    elif album_images is not NODATA:
                        self.lastfm.getTopAlbumsImage(album, size=pylast.COVER_MEDIUM)

            similar = self.infoCache[artist].get(SIMILAR_ARTISTS)
            if not similar:
                self.lastfm.getSimilar(artist)
            elif similar is not NODATA:
                self.infoText.setSimilarArtists(similar)
        else:
            self.lastfm.getBio(artist, True)
            self.lastfm.getImage(artist, size=pylast.COVER_LARGE)
            self.lastfm.getTopAlbums(artist)
            self.lastfm.getTopTracks(artist)
            self.lastfm.getSimilar(artist)
            self.lastfm.getTags(artist)

        self.history.newPage(self.infoText)
        self.infoTextArea.setHtml(self.infoText.str())
        self.infoCache[artist][PAGE] = self.infoText

    def showTrack(self, track, album_title='', count=None):
        if self.currentObject == track:
            return
        self.refreshBtn.setEnabled(True)
        self.currentObject = track
        if not album_title or album_title == '_':
            try:
                track = self.lastfm.get_track(track.artist, track.title)
                album_title = track.album_object.title
                self.currentObject = track
            except:
                pass
        self.currentArgs = album_title, count
        if self.checkPageCache(track):
            self.history.newPage(self.infoText)
            self.infoText = self.infoCache[track][PAGE]
            self.infoTextArea.setHtml(self.infoText.str())
            return
        self.infoText = TrackHtml(track, count)
        if track in self.infoCache:
            track_info = self.infoCache[track].get(TRACK_INFO)
            if not track_info:
                self.lastfm.getTrackInfo(track)
            elif track_info is not NODATA:
                self.infoText.setTrackInfo(track_info)
            track_correction = self.infoCache[track].get(CORRECTION)
            if not track_correction:
                self.lastfm.getCorrection(track)
            elif track_correction is not NODATA:
                self.infoText.setCorrection(track_correction)
        else:
            self.lastfm.getTrackInfo(track)
            self.lastfm.getCorrection(track)
        if album_title:
            if not track.album_object or (track.album_object and track.album_object.title != album_title):
                album = self.lastfm.get_album(track.artist, album_title)
                track.album_object = album
            else:
                album = track.album_object
            if album in self.infoCache:
                album_tracks = self.infoCache[album].get(ALBUM_TRACKS)
                if not album_tracks:
                    self.lastfm.getTracks(album)
                elif album_tracks is not NODATA:
                    self.infoText.setAlbumTracks(album_tracks)

                album_info = self.infoCache[album].get(ALBUM_INFO)
                if not album_info:
                    self.lastfm.getAlbumInfo(album)
                elif album_info is not NODATA:
                    self.infoText.setAlbumInfo(album_info)
                if any((album_tracks, album_info)):
                    self.infoText.setAlbum(album.title)

                cover_images = self.infoCache[album].get(COVER_IMAGE)
                if not cover_images:
                    self.lastfm.getImage(album)
                elif cover_images is not NODATA:
                    cover_name = cover_images[pylast.COVER_LARGE]
                    if cover_name:
                        self.infoText.setCover(cover_name)
                    else:
                        self.lastfm.getImage(album)
            else:
                self.lastfm.getTracks(album)
                self.lastfm.getAlbumInfo(album)
                self.lastfm.getImage(album)

        if track.artist in self.infoCache:
            artist_info = self.infoCache[track.artist].get(ARTIST_INFO)
            if not artist_info:
                self.lastfm.getBio(track.artist)
            elif artist_info is not NODATA:
                self.infoText.setArtistInfo(artist_info)
            artist_images = self.infoCache[track.artist].get(ARTIST_IMAGE)
            if not artist_images:
                self.lastfm.getImage(track.artist)
            elif artist_images is not NODATA:
                artist_image_name = artist_images.get(pylast.COVER_MEDIUM)
                if artist_image_name:
                    self.infoText.setArtistImage(artist_image_name)
                else:
                    self.lastfm.getImage(track.artist)
        else:
            self.lastfm.getBio(track.artist)
            self.lastfm.getImage(track.artist)

        self.history.newPage(self.infoText)
        self.infoTextArea.setHtml(self.infoText.str())
        self.infoCache[track][PAGE] = self.infoText

    def albumReceivedForTrack(self, album, track):
        if isinstance(self.currentObject, (pylast.Tag, pylast.Artist)):
            if track in [top.item for top in self.currentObject.get_top_tracks(limit=10)]:
                self.infoText.setTopTrackAlbum(track)
                if len(self.infoText.top_tracklist_albums) == len(self.infoText.top_tracklist):
                    self.infoTextArea.setHtml(self.infoText.str())

    def infoCacheUpdate(self, info, obj, info_type):
        def setCache(info=None):
            try:
                self.infoCache[obj][info_type] = info
            except:
                self.infoCache[obj] = {info_type: info}

        if info_type in (ARTIST_IMAGE, COVER_IMAGE, TOP_ALBUM_IMAGE):
            if info:
                url = QtCore.QUrl(info[0])
                size = info[1]
                info = '{}/{}'.format(size, url.fileName())
                downloader = ImageDownloader(self, url)
                downloader.imageReceived.connect(lambda image, name=info, info_type=info_type, obj=obj: self.imageCacheUpdate(image, name, info_type, obj))
                try:
                    img_dict = self.infoCache[obj][info_type]
                except:
                    img_dict = {}
                    self.infoCache[obj][info_type] = img_dict
                img_dict[size] = info
            else:
                setCache(info=NODATA)
            return
        elif info_type == CORRECTION:
            previous = obj.name if isinstance(obj, pylast.Artist) else obj.title
            if previous == info:
                setCache(info=NODATA)
            else:
                if isinstance(obj, pylast.Artist):
                    obj.name = info
                else:
                    obj.title = info
                setCache(info=previous)
            return
        elif info_type == TOP_ALBUMS:
            album_items = info[:]
            info = []
            for item in album_items:
                album = item.item
                info.append(album)
                if album in self.infoCache:
                    album_images = self.infoCache[album].get(COVER_IMAGE)
                    if album_images and album_images.get(pylast.COVER_MEDIUM):
                        self.infoText.setTopAlbumImage(album, album_images[pylast.COVER_MEDIUM])
                    elif album_images is not NODATA:
                        self.lastfm.getTopAlbumsImage(album, size=pylast.COVER_MEDIUM)
                else:
                    self.infoCache[album] = {info_type: {}}
                    self.lastfm.getTopAlbumsImage(album, size=pylast.COVER_MEDIUM)
        elif info_type == TOP_TRACKS:
            track_items = info[:]
            info = []
            for track in track_items:
                info.append(track)
                if track in self.infoCache:
                    self.infoText.setTopTrackAlbum(track)
                else:
                    self.lastfm.getAlbumObject(track)
        elif info_type == SIMILAR_ARTISTS:
            similar_items = info[:]
            info = []
            for item in similar_items:
                similar = item.item
                info.append(similar)
        elif info_type in (TOP_ARTISTS, TOP_TRACKS):
            tags = info[:]
            info = []
            for item in tags:
                tag = item.item
                info.append(tag)
        if not info:
            setCache(info=NODATA)
            return
        setCache(info=info)
        if self.currentObject == obj:
            self.infoText.setData(info, info_type)
        elif isinstance(obj, pylast.Artist):
            if (isinstance(self.currentObject, (pylast.Track, pylast.Album)) and self.currentObject.artist == obj) or \
                    (isinstance(self.currentObject, pylast.Artist) and self.currentObject == obj):
                self.infoText.setData(info, info_type)
        elif isinstance(obj, pylast.Album) and isinstance(self.currentObject, pylast.Track) and self.currentObject.album_object == obj:
            self.infoText.setAlbum(obj.title)
            self.infoText.setData(info, info_type)
        pos = self.infoTextArea.verticalScrollBar().value()
        self.infoTextArea.setHtml(self.infoText.str())
        self.infoTextArea.verticalScrollBar().setValue(pos)

    def imageCacheUpdate(self, image, name, info_type, obj):
        if image.isNull():
            return
        self.infoTextArea.document().addResource(QtGui.QTextDocument.ImageResource, QtCore.QUrl('file://{}'.format(name)), QtCore.QVariant(image))
        if info_type == TOP_ALBUM_IMAGE:
            #prevent unwanted calls for top album images
            if isinstance(self.currentObject, pylast.Artist) and self.currentObject == obj.artist:
                self.infoText.setTopAlbumImage(name, obj)
            elif isinstance(self.currentObject, pylast.Tag):
                if obj in [top.item for top in self.currentObject.get_top_albums(limit=10)]:
                    self.infoText.setTopAlbumImage(name, obj)
        elif self.currentObject == obj or \
                (info_type == ARTIST_IMAGE and \
                (isinstance(self.currentObject, (pylast.Track, pylast.Album)) and self.currentObject.artist == obj)) or \
                (info_type == COVER_IMAGE and \
                (isinstance(self.currentObject, pylast.Track) and self.currentObject.album_object == obj)):
#                (info_type == TOP_ALBUM_IMAGE and \
#                (isinstance(self.currentObject, pylast.Artist) and self.currentObject == obj.artist)):
            self.infoText.setData(name, info_type, obj)
        pos = self.infoTextArea.verticalScrollBar().value()
        self.infoTextArea.setHtml(self.infoText.str())
        self.infoTextArea.verticalScrollBar().setValue(pos)

    def userCheckStart(self, *args):
        self.userCheckTimer.start()
        self.retrieveUserEdit.setStyleSheet('')
        self.retrieveBtn.setEnabled(False)

    def userCheck(self, valid):
        if valid:
            self.retrieveUserEdit.setStyleSheet('')
            self.retrieveBtn.setEnabled(True)
            self.currentUser = self.retrieveUserEdit.text()
        else:
            self.retrieveUserEdit.setStyleSheet('color: red;')
            self.retrieveBtn.setEnabled(False)
            self.currentUser = ''

    def updateViews(self):
        self.trackTreeView.setSortingEnabled(True)
        self.trackTreeView.resizeColumnToContents(0)
        self.trackTreeView.resizeColumnToContents(1)

        self.trackTable.resizeColumnsToContents()
        self.trackTable.resizeRowsToContents()
        self.trackTable.verticalHeader().setVisible(False)
        self.trackTable.setHorizontalScrollMode(self.trackTable.ScrollPerPixel)
        self.trackTable.setSortingEnabled(True)
        self.trackModel.setHorizontalHeaderLabels(['Title', 'Artist', 'Album', 'N', 'Date'])
        [self.trackTable.horizontalHeader().resizeSection(s, 150) for s in xrange(3)]
        self.trackTable.resizeColumnToContents(3)
        self.trackTable.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)

        self.artistCounter.setText('Artists: {}'.format(self.trackTreeModel.rowCount()))
        self.trackCounter.setText('Tracks: {}'.format(self.trackModel.rowCount()))

    def reset(self):
        self.track_dict = {}
        self.track_data = []
        self.track_times = {x:0 for x in xrange(24)}
        self.times_dict = [(h, QtCore.QTime(h + 1, 0)) for h in xrange(23)]
        self.track_days = {d:0 for d in xrange(1, 8)}
        self.track_years = {}
        self.trackCount = 0
        self.topTracks = {}
        self.topArtists = {}
        self.topAlbums = {}
        self.scrobbleHistory = {}

    def updateTracks(self):
        def delayedLimit():
            for track_group, total_pages, is_final in self.lastfm.user.get_recent_tracks_yield(limit=None, page_limit=1, time_from=after):
                break
            self.retrieveMsgBox.setLimit(total_pages)
        self.latestAdded = 0
        latest_item = self.trackModel.item(0, 4)
        if not latest_item:
            return
        dates = latest_item.data(DATE_ROLE)
        latest = sorted(dates, reverse=True)[0]
        self.retrieveMsgBox.show(updating=True)
        self.lastfm.setUser(self.retrieveUserEdit.text(), False)
        self.retrieveMsgBox.setLimit()
        QtCore.QTimer.singleShot(0, delayedLimit)
        after = latest.toMSecsSinceEpoch() / 1000 + 30
        self.lastfm.retrieve(after=after)

    def retrieve(self):
        if len(self.track_data) > 100:
            res = QtWidgets.QMessageBox.question(
                self, 'Reset and retrieve?', 
                'You already have more than 2000 tracks statistics, retrieving again will reset everything.\
                \nDo you want to proceed?'
                )
            if res == QtWidgets.QMessageBox.No:
                return
        self.reset()
        self.saveBtn.setEnabled(False)
        self.trackYearsWidget.reset()
        self.trackTimesWidget.reset()
        self.trackWeekdaysWidget.reset()
        self.trackModel.clear()
        self.trackTreeModel.clear()
        self.trackTreeModel.setHorizontalHeaderLabels(['', 'Plays', 'Dates'])
        self.lastfm.setUser(self.retrieveUserEdit.text(), False)
        self.playCount = self.lastfm.playCount()
        self.retrieveMsgBox.show()
        if self.retrieveLimitCheck.isChecked():
            #retrieve n+(n/50) because every page might contain the now playing track, fix this
            self.lastfm.retrieve(limit=self.retrieveLimitSpin.value() + (self.retrieveLimitSpin.value()/50))
            self.retrieveMsgBox.setLimit(self.retrieveLimitSpin.value())
        else:
            self.lastfm.retrieve(limit=None)
            self.retrieveMsgBox.setLimit(self.playCount)

    def updateStats(self, track, album, timestamp, qdate):
        self.scrobbleHistory[timestamp] = (track, album, qdate)
        time = qdate.time()
        date = qdate.date()
        month = date.month() - 1
        self.track_days[date.dayOfWeek()] += 1
        for hour, qtime in self.times_dict:
            if time < qtime:
                self.track_times[hour] += 1
                break
        else:
            self.track_times[23] += 1
        try:
            self.track_years[date.year()][month] += 1
        except:
            self.track_years[date.year()] = [0 if m != month else 1 for m in xrange(12)]
        try:
            self.topTracks[track] += 1
        except:
            self.topTracks[track] = 1
        try:
            self.topArtists[track.artist] += 1
        except:
            self.topArtists[track.artist] = 1
        try:
            self.topAlbums[(track.artist, album)] += 1
        except:
            self.topAlbums[(track.artist, album)] = 1

    def computePeriodStats(self):
        track_days = {d:0 for d in xrange(1, 8)}
        track_times = {x:0 for x in xrange(24)}
        topTracks = {}
        topArtists = {}
        topAlbums = {}

        start = self.startDateEdit.dateTime()
        end = self.endDateEdit.dateTime()
        start_timestamp = start.toMSecsSinceEpoch() / 1000
        end_timestamp = end.toMSecsSinceEpoch() / 1000
        history_timestamps = sorted(self.scrobbleHistory.keys())
        for index in xrange(bisect_left(history_timestamps, start_timestamp), bisect_right(history_timestamps, end_timestamp)):
            timestamp = history_timestamps[index]
            track, album, qdate = self.scrobbleHistory[timestamp]
            time = qdate.time()
            date = qdate.date()
            track_days[date.dayOfWeek()] += 1
            for hour, qtime in self.times_dict:
                if time < qtime:
                    track_times[hour] += 1
                    break
            else:
                track_times[23] += 1
            try:
                topTracks[track] += 1
            except:
                topTracks[track] = 1
            try:
                topArtists[track.artist] += 1
            except:
                topArtists[track.artist] = 1
            try:
                topAlbums[(track.artist, album)] += 1
            except:
                topAlbums[(track.artist, album)] = 1
        self.periodTopTextArea.setStats(topTracks, topArtists, topAlbums)
        self.periodTrackTimesWidget.setTimes(track_times)
        self.periodWeekTimesWidget.setDays(track_days)

    def closeEvent(self, event):
        if self.saveBtn.isEnabled():
            res = QtWidgets.QMessageBox.question(
                self, 'Save statistics?', 
                'Statistics have been updated but not stored.\n'
                'Do you want to save them, ignore and close or go back to Lastats.fm?', 
                QtWidgets.QMessageBox.Save|QtWidgets.QMessageBox.Ignore|QtWidgets.QMessageBox.Cancel
                )
            if res == QtWidgets.QMessageBox.Cancel:
                event.ignore()
                return
            if res == QtWidgets.QMessageBox.Save:
                self.saveData()
        if self.currentUser:
            self.settings.setValue('user', self.currentUser)
            self.settings.sync()
        QtWidgets.QMainWindow.closeEvent(self, event)

    def tracksReceived(self, data, after=None, enable_save=True):
        self.updateBtn.setEnabled(True)
        self.trackTable.setSortingEnabled(False)
        self.trackTreeView.setSortingEnabled(False)
        self.saveBtn.setEnabled(enable_save)
        insert_pos = self.latestAdded
        for track, album, timestamp in data:
            self.track_data.append((track, album, timestamp))
            title = track.title
            artist_name = track.artist.name
            qdate = QtCore.QDateTime.fromMSecsSinceEpoch(timestamp * 1000)
            self.updateStats(track, album, timestamp, qdate)
            qdate_str = qdate.toString('yy/MM/dd hh:mm')
            
            track_info = title, artist_name, album
            track_data = self.track_dict.get(track_info)
            if track_data is None:
                self.track_dict[track_info] = [self.trackModel.rowCount(), 1, [qdate_str], track]
                title_item = QtGui.QStandardItem(title)
                title_item.setData(track, OBJECT_ROLE)
                artist_item = QtGui.QStandardItem(artist_name)
                album_item = QtGui.QStandardItem(album)
                count_item = QtGui.QStandardItem('1')
                count_item.setData(1, COUNT_ROLE)
                date_item = QtGui.QStandardItem(qdate_str)
                date_item.setData([qdate], DATE_ROLE)
                if after:
                    self.trackModel.insertRow(insert_pos, [title_item, artist_item, album_item, count_item, date_item])
                    insert_pos += 1
                    self.latestAdded = insert_pos
                else:
                    self.trackModel.appendRow([title_item, artist_item, album_item, count_item, date_item])
            else:
                self.track_dict[track_info][1] += 1
                self.track_dict[track_info][2].insert(0, qdate_str)
                count_item = self.trackModel.item(track_data[0], 3)
                count_item.setText(str(self.track_dict[track_info][1]))
                count_item.setData(self.track_dict[track_info][1], COUNT_ROLE)
                date_item = self.trackModel.item(track_data[0], 4)
                dates = date_item.data(DATE_ROLE)
                dates.append(qdate)
                date_item.setData(dates, DATE_ROLE)
                date_item.setText('{}, {}'.format(date_item.text(), qdate_str))
                self.trackModel.item(track_data[0], 4).setText(', '.join(self.track_dict[track_info][2]))

            found_artist = self.trackTreeModel.match(self.trackTreeModel.index(0, 0), QtCore.Qt.DisplayRole, artist_name, -1, QtCore.Qt.MatchFixedString)
            if not found_artist:
                artist_tree = QtGui.QStandardItem(artist_name)
                artist_tree.setData(track.artist, OBJECT_ROLE)
                artist_tree.setData(1, COUNT_ROLE)
                album_tree = QtGui.QStandardItem(album)
                album_tree.setData(None, OBJECT_ROLE)
                album_count_item = QtGui.QStandardItem('1')
                album_count_item.setData(1, COUNT_ROLE)
                artist_tree.appendRow([album_tree, album_count_item])
                title_item = QtGui.QStandardItem(title)
                title_item.setData(track, OBJECT_ROLE)
                count_item = QtGui.QStandardItem('1')
                count_item.setData(1, COUNT_ROLE)
                date_item = QtGui.QStandardItem(qdate_str)
                date_item.setData([qdate], DATE_ROLE)
                album_tree.appendRow([title_item, count_item, date_item])
                self.trackTreeModel.appendRow([artist_tree, count_item.clone()])
            else:
                artist_index = found_artist[0]
                artist_tree = self.trackTreeModel.itemFromIndex(artist_index)
                artist_count = self.trackTreeModel.item(artist_index.row(), 1)
                count = artist_count.data(COUNT_ROLE) + 1
                artist_count.setText(str(count))
                artist_count.setData(count, COUNT_ROLE)
                found_album = self.trackTreeModel.match(artist_index.child(0, 0), QtCore.Qt.DisplayRole, album, -1, QtCore.Qt.MatchFixedString)
                if not found_album:
                    album_tree = QtGui.QStandardItem(album)
                    album_tree.setData(None, OBJECT_ROLE)
                    album_count_item = QtGui.QStandardItem('1')
                    album_count_item.setData(1, COUNT_ROLE)
                    artist_tree.appendRow([album_tree, album_count_item])
                    title_item = QtGui.QStandardItem(title)
                    title_item.setData(track, OBJECT_ROLE)
                    count_item = QtGui.QStandardItem('1')
                    count_item.setData(1, COUNT_ROLE)
                    date_item = QtGui.QStandardItem(qdate_str)
                    date_item.setData([qdate], DATE_ROLE)
                    album_tree.appendRow([title_item, count_item, date_item])
                else:
                    album_index = found_album[0]
                    album_count_item = self.trackTreeModel.itemFromIndex(album_index.sibling(album_index.row(), 1))
                    album_count = album_count_item.data(COUNT_ROLE) + 1
                    album_count_item.setData(album_count, COUNT_ROLE)
                    album_count_item.setText(str(album_count))
                    album_tree = self.trackTreeModel.itemFromIndex(album_index)
                    found_track = self.trackTreeModel.match(album_index.child(0, 0), QtCore.Qt.DisplayRole, title, -1, QtCore.Qt.MatchFixedString)
                    if not found_track:
                        title_item = QtGui.QStandardItem(title)
                        title_item.setData(track, OBJECT_ROLE)
                        count_item = QtGui.QStandardItem('1')
                        count_item.setData(1, COUNT_ROLE)
                        date_item = QtGui.QStandardItem(qdate_str)
                        date_item.setData([qdate], DATE_ROLE)
                        album_tree.appendRow([title_item, count_item, date_item])
                    else:
                        title_index = found_track[0]
                        count_item = album_tree.child(title_index.row(), 1)
                        count = count_item.data(COUNT_ROLE) + 1
                        count_item.setData(count, COUNT_ROLE)
                        count_item.setText(str(count))
                        date_item = album_tree.child(title_index.row(), 2)
                        dates = date_item.data(DATE_ROLE)
                        dates.append(qdate)
                        date_item.setData(dates, DATE_ROLE)
                        date_item.setText('{}, {}'.format(date_item.text(), qdate_str))

        self.updateViews()
        self.trackTimesWidget.setTimes(self.track_times)
        self.trackYearsWidget.setYears(self.track_years)
        self.trackWeekdaysWidget.setDays(self.track_days)
        self.topTextArea.setStats(self.topTracks, self.topArtists, self.topAlbums)
        self.trackCount += len(data)
#        self.retrieveMsgBox.setInformativeText('{}/{}'.format(self.trackCount, self.retrieveLimitSpin.value() if self.retrieveLimitCheck.isChecked() else self.playCount))
        self.retrieveMsgBox.tracksAdded(len(data))
#        if self.retrieveLimitCheck.isChecked():
#            if self.trackCount >= self.retrieveLimitSpin.value():
#                self.retrieveMsgBox.hide()
#        elif self.trackCount >= self.playCount:
#            self.retrieveMsgBox.hide()
        self.trackTable.setSortingEnabled(True)
        self.trackTreeView.setSortingEnabled(True)
        timestamps = sorted(self.scrobbleHistory.keys())
        first = QtCore.QDateTime.fromMSecsSinceEpoch(min(timestamps) * 1000).date()
        last = QtCore.QDateTime.fromMSecsSinceEpoch(max(timestamps) * 1000).date().addDays(1)
        self.setPeriodRanges(first, last)

    def getFromCSV(self):
        with open('MaurizioB.csv', 'r') as source:
            self.tracks = [d for d in csv.reader(source, delimiter=',')]

        uslocale = QtCore.QLocale(QtCore.QLocale.English, QtCore.QLocale.UnitedStates)
        old_date = uslocale.toString(QtCore.QDateTime.currentDateTimeUtc(), 'dd MMM yyyy hh:mm')
        track_dict = {}
        current = self.tracks[0]
        total = len(self.tracks)
        for id, track in enumerate(self.tracks):
            if track == current:
                continue
            artist, album, title, date = track
            track_info = (title, artist, album)
            if not date:
                date = old_date
            else:
                old_date = date
#            qdate = QtCore.QDateTime.fromString(date, 'dd MMM yyyy hh:mm')
            qdate = uslocale.toDateTime(date, 'dd MMM yyyy hh:mm')
            qdate = qdate.addSecs(qdate.offsetFromUtc())
            qdate_str = qdate.toString('yy/MM/dd hh:mm')

            track_data = track_dict.get(track_info)
            if track_data is None:
                track_dict[track_info] = [self.trackModel.rowCount(), 1, [qdate_str]]
                artist_item = QtGui.QStandardItem(artist)
                album_item = QtGui.QStandardItem(album)
                title_item = QtGui.QStandardItem(title)
                count_item = QtGui.QStandardItem('1')
                count_item.setData(1, COUNT_ROLE)
                date_item = QtGui.QStandardItem(qdate_str)
                self.trackModel.appendRow([title_item, artist_item, album_item, count_item, date_item])
            else:
                track_dict[track_info][1] += 1
                track_dict[track_info][2].insert(0, qdate_str)
                count_item = self.trackModel.item(track_data[0], 3)
                count_item.setText(str(track_dict[track_info][1]))
                count_item.setData(track_dict[track_info][1], COUNT_ROLE)
                self.trackModel.item(track_data[0], 4).setText(', '.join(track_dict[track_info][2]))

            found_artist = self.trackTreeModel.match(self.trackTreeModel.index(0, 0), QtCore.Qt.DisplayRole, artist, -1, QtCore.Qt.MatchFixedString)
            if not found_artist:
                artist_tree = QtGui.QStandardItem(artist)
                artist_tree.setData(1, COUNT_ROLE)
                album_tree = QtGui.QStandardItem(album)
                album_count_item = QtGui.QStandardItem('1')
                album_count_item.setData(1, COUNT_ROLE)
                artist_tree.appendRow([album_tree, album_count_item])
                title_item = QtGui.QStandardItem(title)
                count_item = QtGui.QStandardItem('1')
                count_item.setData(1, COUNT_ROLE)
                date_item = QtGui.QStandardItem(qdate_str)
                album_tree.appendRow([title_item, count_item, date_item])
                self.trackTreeModel.appendRow([artist_tree, count_item.clone()])
            else:
                artist_index = found_artist[0]
                artist_tree = self.trackTreeModel.itemFromIndex(artist_index)
                artist_count = self.trackTreeModel.item(artist_index.row(), 1)
                count = artist_count.data(COUNT_ROLE) + 1
                artist_count.setText(str(count))
                artist_count.setData(count, COUNT_ROLE)
                found_album = self.trackTreeModel.match(artist_index.child(0, 0), QtCore.Qt.DisplayRole, album, -1, QtCore.Qt.MatchFixedString)
                if not found_album:
                    album_tree = QtGui.QStandardItem(album)
                    album_count_item = QtGui.QStandardItem('1')
                    album_count_item.setData(1, COUNT_ROLE)
                    artist_tree.appendRow([album_tree, album_count_item])
                    title_item = QtGui.QStandardItem(title)
                    count_item = QtGui.QStandardItem('1')
                    count_item.setData(1, COUNT_ROLE)
                    date_item = QtGui.QStandardItem(qdate_str)
                    album_tree.appendRow([title_item, count_item, date_item])
                else:
                    album_index = found_album[0]
                    album_count_item = self.trackTreeModel.itemFromIndex(album_index.sibling(album_index.row(), 1))
                    album_count = album_count_item.data(COUNT_ROLE) + 1
                    album_count_item.setData(album_count)
                    album_count_item.setText(str(album_count))
                    album_tree = self.trackTreeModel.itemFromIndex(album_index)
                    found_track = self.trackTreeModel.match(album_index.child(0, 0), QtCore.Qt.DisplayRole, title, -1, QtCore.Qt.MatchFixedString)
                    if not found_track:
                        title_item = QtGui.QStandardItem(title)
                        count_item = QtGui.QStandardItem('1')
                        count_item.setData(1, COUNT_ROLE)
                        date_item = QtGui.QStandardItem(qdate_str)
                        album_tree.appendRow([title_item, count_item, date_item])
                    else:
                        title_index = found_track[0]
                        count_item = album_tree.child(title_index.row(), 1)
                        count = count_item.data(COUNT_ROLE) + 1
                        count_item.setData(count, COUNT_ROLE)
                        count_item.setText(str(count))

            if not id%500:
                print '{}/{}'.format(id, total)
#            if id > 30000:
#                self.trackTreeView.showColumn(1)
#                break

    def tableMenuEvent(self, event):
        index = self.trackTable.indexAt(event.pos())
        menu = QtWidgets.QMenu()
        text = index.data()
        hide_item = QtWidgets.QAction('Hide "{}"'.format(text), menu)
        restore_item = QtWidgets.QAction('Restore all', menu)
        menu.addActions([hide_item, restore_item])
        res = menu.exec_(self.mapToGlobal(event.pos()))
        if res == hide_item:
            items = self.trackModel.findItems(index.data(), column=index.column())
            for item in items:
                self.trackTable.setRowHidden(item.row(), True)
        elif res == restore_item:
            for row in xrange(self.trackModel.rowCount()):
                self.trackTable.setRowHidden(row, False)


def main():
    argv = sys.argv[:]
    argv[0] = 'Lastats.fm'
    app = QtWidgets.QApplication(argv)
    app.setOrganizationName('jidesk')
    app.setApplicationName('Lastats')

    win = LaStats(app)
    win.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()




