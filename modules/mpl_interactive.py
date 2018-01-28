import copy

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from PyQt4 import QtCore

class Interact(QtCore.QObject):
    hovering = QtCore.pyqtSignal(int)
    def __init__(self):
        super(Interact, self).__init__()
        self._highlighted = {}
        self._persistent_highlights = []
        self.highlight = False
        self._connected = {}
        self._artist_type = {}
        self._canvas_todraw = None

    def set_highlight(self, highlight):
        """
        Enable or disable artist highlighting on hover.
        """
        self.highlight = highlight

    def set_dimming(self, dim):
        """
        Enable or disable dimming of artists not being hovered.
        """
        self.dim = dim

    def update(self, axes, artist_type=None):
        """
        Update artists on canvas if new ones have been added or old ones
        deleted.
        """
        if axes not in self._connected:
            return

        if self._artist_type[axes]:
            artist_type = self._artist_type[axes]
            
        if artist_type:
            if artist_type.lower() in ('lines', 'line', 'line2d'):
                self.artists = axes.lines
            elif artist_type.lower() in ('scatter', 'collections'):
                self.artists = axes.collections
            elif artist_type.lower() in ('patches', 'patch', 'span', 'spans'
                                         'axvspan', 'axhspan'):
                self.artists = axes.patches
            else:
                # unknown artist type
                pass
        else:
            self.artists = axes.lines + axes.collections + axes.patches
        
    def connect(self, axes, artist_type=None):
        """
        Connect an axes to the hover callback function. Only artists of type
        <artist_type> will be affected.
        """
        cid = axes.figure.canvas.mpl_connect('motion_notify_event',
                                             self.on_plot_hover)
        self._connected[axes] = cid
        self._artist_type[axes] = artist_type
        self.update(axes, artist_type)

    def disconnect(self, axes=None):
        if axes:
            if axes not in self._connected:
                return
            cid = self._connected[axes]
            axes.figure.canvas.mpl_disconnect(cid)           
            del self._connected[axes]
            del self._artist_type[axes]
        else:
            for axes, cid in self._connected.items():
                axes.figure.canvas.mpl_disconnect(cid)           
            self._connected = {}
            self._artist_type = {}

    def on_plot_hover(self, event):
        """
        Callback function when hovering over canvas. Check if any artist is
        being hovered over and delegate appropriate response.
        """
        for artist in self.artists:
            if artist.contains(event)[0]:
                self.hovering.emit(artist.get_label())
                print artist.get_label()
                if self.highlight:
                    self._highlight(artist)
                if self.dim:
                    self._dim(artist)
            else:
                if not artist in self._persistent_highlights:
                    self._remove_highlight(artist)
                if self.dim:
                    self._undim(artist)
        if self._canvas_todraw:
            self._canvas_todraw.draw()

    def _dim(self, artist):
        for oartist in self.artists:
            if oartist == artist:
                continue
            alpha = oartist.get_alpha() or 1
            oartist.set_alpha(alpha / 2.)
            if oartist.figure:
                self._canvas_todraw = oartist.figure.canvas

    def _undim(self, artist):
        for oartist in self.artists:
            if oartist == artist:
                continue
            alpha = oartist.get_alpha() or 1
            oartist.set_alpha(min(alpha * 2., 1))
            if oartist.figure:
                self._canvas_todraw = oartist.figure.canvas

    def _is_highlighted(self, artist):
        return artist.get_label() in self._highlighted.keys()

    def _highlight(self, artist):
        """
        Highlight if not highlighted yet.
        """
        if not self._is_highlighted(artist):
            orig_kwargs = self._replot(artist, highlight=True)
            self._highlighted[artist.get_label()] = orig_kwargs
            self._canvas_todraw = artist.figure.canvas

    def _remove_highlight(self, artist):
        """
        Remove highlight if highlighted.
        """
        if self._is_highlighted(artist):
            print "removing highlight"
            self._replot(artist, highlight=False)
            del self._highlighted[artist.get_label()]
            self._canvas_todraw = artist.figure.canvas

    def _get_highlight_kwargs(self, artist):
        artistinfo = ArtistInfoExtracter()
        artist_type = artistinfo.get_artist_type(artist)
        if artist_type == 'Line2D':
            hi_kwargs = {
                'lw': artist.get_lw() * 2,
                'alpha': 1}
        elif artist_type == 'PathCollection':
            hi_kwargs = {
                'linewidths': [lw * 2 or 2 for lw in artist.get_linewidths()],
                'alpha': 1}
        #elif artist_type == 'Polygon':
        #    hi_kwargs = {
        #        'linewidth': artist.get_linewidth() * 2,
        #        'alpha': 1}
        return hi_kwargs

    def _replot(self, artist, highlight):
        """
        Remove the artist from the canvas and replot it highlighting it if
        <higlight> is True. Return kwargs of artist before the highlighting
        changed.
        """
        artistinfo = ArtistInfoExtracter()
        artist_type = artistinfo.get_artist_type(artist)
        orig_kwargs = artistinfo.get_artist_kwargs(artist)
        xy = artistinfo.get_artist_xydata(artist)
        if xy is None:
            return
        x, y = xy
        axes = artist.axes
        gid = artist.get_label()

        if highlight:
            kwargs = copy.copy(orig_kwargs)
            kwargs.update(self._get_highlight_kwargs(artist))
        else:
            kwargs = self._highlighted[gid]

        print artist.__repr__()
        try:
            artist.remove()
            print "Removed artist", gid
        except ValueError:
            # If the artist isn't actually there (this does happen for some
            # reason)
            print "Cannot remove artist", gid
            pass
        self.artists = [a for a in self.artists if a != artist]
        del artist
        if not axes:
            # Sometimes the artist doesn't have axes for some reason
            print "Artist", gid, "had no axes"
            return
        print "replotting", gid
        if artist_type == 'Line2D':
            newartist, = axes.plot(x, y, **kwargs)
        elif artist_type == 'PathCollection':
            newartist = axes.scatter(x, y, **kwargs)
        #elif artist_type == 'Polygon':
        #    newartist = mpatches.Polygon([x, y], **kwargs)
        #elif artist_type == 'Rectangle':
        #    xmin, xmax = x
        #    ymin, ymax = y
        #    verts = [(xmin, ymin), (xmin, ymax), (xmax, ymax), (xmax, ymin)]
        #    newartist = mpatches.Polygon(verts, **kwargs)
        self.artists.append(newartist)
        return orig_kwargs


class ArtistInfoExtracter():
    def get_artist_type(self, artist):
        """
        Get artist type
        """
        return type(artist).__name__

    def get_artist_color(self, artist):
        """
        Get artist color. Only main color supported.
        """
        artist_type = self.get_artist_type(artist)
        color = None
        if artist_type == 'Line2D':
            color = artist.get_color()
        elif artist_type == 'PathCollection':
            color = artist.get_facecolor()
        #elif artist_type == 'Polygon':
        #    color = artist.get_facecolor()
        return color

    def get_artist_xydata(self, artist):
        """
        Get artist xy data and return it transposed so that it's ready to be
        expandet into x and y and to be plotted again.
        """
        artist_type = self.get_artist_type(artist)
        if artist_type == 'Line2D':
            xydata = artist.get_xydata()
        elif artist_type == 'PathCollection':
            xydata = artist.get_offsets()
        #elif artist_type == 'Polygon':
        #    xydata = artist.get_xy()
        #elif artist_type == 'Rectangle':
        #    xydata = artist.get_xy()
        else:
            print "Unknown artist type", artist_type
            xydata = None
        if xydata is None:
            return
        return xydata.transpose()

    def get_artist_kwargs(self, artist):
        artist_type = self.get_artist_type(artist)
        if artist_type == 'Line2D':
            params = {'color': artist.get_color(),
                      'alpha': artist.get_alpha(),
                      'agg_filter': artist.get_agg_filter(),
                      'animated': artist.get_animated(),
                      #'aa': artist.get_aa(),
                      'dash_capstyle': artist.get_dash_capstyle(),
                      'dash_joinstyle': artist.get_dash_joinstyle(),
                      'drawstyle': artist.get_drawstyle(),
                      'fillstyle': artist.get_fillstyle(),
                      'label': artist.get_label(),
                      'ls': artist.get_ls(),
                      'lw': artist.get_lw(),
                      'marker': artist.get_marker(),
                      'mec': artist.get_mec(),
                      'mew': artist.get_mew(),
                      'mfc': artist.get_mfc(),
                      'mfcalt': artist.get_mfcalt(),
                      'ms': artist.get_ms(),
                      'markevery': artist.get_markevery(),
                      'pickradius': artist.get_pickradius(),
                      'rasterized': artist.get_rasterized(),
                      'sketch_params': artist.get_sketch_params(),
                      'snap': artist.get_snap(),
                      'solid_capstyle': artist.get_solid_capstyle(),
                      'solid_joinstyle': artist.get_solid_joinstyle(),
                      'transform': artist.get_transform(),
                      'url': artist.get_url(),
                      'visible': artist.get_visible(),
                      'zorder': artist.get_zorder(),
                      'picker': artist.get_picker()
                      }
        elif artist_type == 'PathCollection':
            params = {'alpha': artist.get_alpha(),
                      'agg_filter': artist.get_agg_filter(),
                      'paths': artist.get_paths(),
                      'cmap': artist.get_cmap(),
                      'norm': artist.norm,
                      'linewidths': artist.get_linewidths(),
                      'edgecolors': artist.get_edgecolors(),
                      'facecolors': artist.get_facecolors(),
                      'animated': artist.get_animated(),
                      'label': artist.get_label(),
                      'snap': artist.get_snap(),
                      # This makes scatter disappear
                      #'transform': artist.get_transform(),
                      'url': artist.get_url(),
                      'visible': artist.get_visible(),
                      'zorder': artist.get_zorder(),
                      'pickradius': artist.get_pickradius(),
                      'rasterized': artist.get_rasterized(),
                      'picker': artist.get_picker(),
                      }
        #elif artist_type == 'Polygon':
        #    params = {'alpha': artist.get_alpha(),
        #              'transform': artist.get_patch_transform(),
        #              'linewidth': artist.get_linewidth(),
        #              'linestyle': artist.get_linestyle(),
        #              'facecolor': artist.get_facecolor(),
        #              'edgecolor': artist.get_edgecolor(),
        #              'joinstyle': artist.get_joinstyle(),
        #              'capstyle': artist.get_capstyle(),
        #              'animated': artist.get_animated(),
        #              'label': artist.get_label(),
        #              'rasterized': artist.get_rasterized(),
        #              'transform': artist.get_transform(),
        #              'url': artist.get_url(),
        #              'visible': artist.get_visible(),
        #              'zorder': artist.get_zorder(),
        #              # Rectangles only
        #              #'width': artist.get_width(),
        #              #'height': artist.get_height(),
        #              #'aa': artist.get_aa(),
        #              'snap': artist.get_snap(),
        #              'picker': artist.get_picker(),
        #              'fill': artist.fill,
        #              'clip_on': artist.get_clip_on(),
        #              }
        else:
            params = {}
        return params

if __name__ == '__main__':
    fig = plt.figure()
    plot = fig.add_subplot(111)
    interact = Interact()

    plot.scatter(range(10), range(10))
    plot.plot([el**2 for el in range(10)])
    plot.axvspan(0, 3)
    interact.connect(plot)
    interact.set_highlight(True)
    interact.set_dimming(True)

    plt.show()
