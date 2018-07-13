from __future__ import division, print_function
import numpy as np
import traceback
import matplotlib.pyplot as plt
from matplotlib.text import Text
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle, Ellipse
from matplotlib.figure import Figure
from matplotlib.axes._subplots import Axes
import matplotlib
import uuid
import re

import snap
from snap import TargetWrapper
from change_tracker import ChangeTracker

DIR_X0 = 1
DIR_Y0 = 2
DIR_X1 = 4
DIR_Y1 = 8


class GrabFunctions(object):
    figure = None
    target = None
    dir = None
    snaps = None

    got_artist = False

    def __init__(self, parent, dir, no_height=False):
        self.figure = parent.figure
        self.parent = parent
        print("GrabFunct", type(self), parent)
        self.dir = dir
        self.snaps = []
        self.no_height = no_height

    def on_motion(self, evt):
        if self.got_artist:
            self.movedEvent(evt)
            self.moved = True

    def button_press_event(self, evt):
        self.got_artist = True
        self.moved = False

        self._c1 = self.figure.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.clickedEvent(evt)

    def button_release_event(self, event):
        print("release Event", event)
        if self.got_artist:
            self.got_artist = False
            self.figure.canvas.mpl_disconnect(self._c1)
            self.releasedEvent(event)
            print("release")

    def clickedEvent(self, event):
        self.parent.start_move()
        self.mouse_xy = (event.x, event.y)

        for s in self.snaps:
            s.remove()
        self.snaps = []

        self.snaps = snap.getSnaps(self.targets, self.dir, no_height=self.no_height)

    def releasedEvent(self, event):
        for snap in self.snaps:
            snap.remove()
        self.snaps = []

        self.parent.end_move()

    def movedEvent(self, event):
        if len(self.targets) == 0:
            return

        dx = event.x - self.mouse_xy[0]
        dy = event.y - self.mouse_xy[1]

        keep_aspect = ("control" in event.key.split("+") if event.key is not None else False)
        ignore_snaps = ("shift" in event.key.split("+") if event.key is not None else False)

        self.parent.move([dx, dy], self.dir, self.snaps, keep_aspect_ratio=keep_aspect, ignore_snaps=ignore_snaps)


class GrabbableRectangleSelection(GrabFunctions):
    grabbers = None

    def addGrabber(self, x, y, dir, GrabberClass):
        # add a grabber object at the given coordinates
        self.grabbers.append(GrabberClass(self, x, y, dir))

    def __init__(self, figure):

        self.grabbers = []
        pos = [0, 0, 0, 0]
        self.positions = np.array(pos, dtype=float)
        self.p1 = self.positions[:2]
        self.p2 = self.positions[2:]
        self.figure = figure

        GrabFunctions.__init__(self, self, DIR_X0 | DIR_X1 | DIR_Y0 | DIR_Y1, no_height=True)

        self.addGrabber(0,   0, DIR_X0 | DIR_Y0, GrabberGenericRound)
        self.addGrabber(0.5, 0, DIR_Y0, GrabberGenericRectangle)
        self.addGrabber(1,   1, DIR_X1 | DIR_Y1, GrabberGenericRound)
        self.addGrabber(1, 0.5, DIR_X1, GrabberGenericRectangle)
        self.addGrabber(0,   1, DIR_X0 | DIR_Y1, GrabberGenericRound)
        self.addGrabber(0.5, 1, DIR_Y1, GrabberGenericRectangle)
        self.addGrabber(1,   0, DIR_X1 | DIR_Y0, GrabberGenericRound)
        self.addGrabber(0, 0.5, DIR_X0, GrabberGenericRectangle)

        self.c4 = self.figure.canvas.mpl_connect('key_press_event', self.keyPressEvent)

        self.targets = []
        self.targets_rects = []

        self.hide_grabber()

    def add_target(self, target):
        target = TargetWrapper(target)
        self.targets.append(target)

        new_points = np.array(target.get_positions())

        x0, y0, x1, y1 = np.min(new_points[:, 0]), np.min(new_points[:, 1]), np.max(new_points[:, 0]), np.max(
            new_points[:, 1])
        rect1 = Rectangle((x0, y0), x1 - x0, y1 - y0, picker=False, figure=self.figure, linestyle="-", edgecolor="w",
                          facecolor="#FFFFFF00", zorder=900, label="_rect for %s" % str(target))
        rect2 = Rectangle((x0, y0), x1 - x0, y1 - y0, picker=False, figure=self.figure, linestyle="--", edgecolor="k",
                          facecolor="#FFFFFF00", zorder=900, label="_rect2 for %s" % str(target))
        self.figure.patches.append(rect1)
        self.figure.patches.append(rect2)
        self.targets_rects.append(rect1)
        self.targets_rects.append(rect2)

        points = None
        for target in self.targets:
            new_points = np.array(target.get_positions())

            if points is None:
                points = new_points
            else:
                points = np.concatenate((points, new_points))

        for grabber in self.grabbers:
            grabber.targets = self.targets

        self.positions[0] = np.min(points[:, 0])
        self.positions[1] = np.min(points[:, 1])
        self.positions[2] = np.max(points[:, 0])
        self.positions[3] = np.max(points[:, 1])

        if self.do_target_scale():
            self.update_grabber()
        else:
            self.hide_grabber()

    def update_grabber(self):
        for grabber in self.grabbers:
            grabber.updatePos()

    def hide_grabber(self):
        for grabber in self.grabbers:
            grabber.set_xy((-100, -100))

    def clear_targets(self):
        for rect in self.targets_rects:
            self.figure.patches.remove(rect)
        self.targets_rects = []
        self.targets = []

        self.hide_grabber()

    def do_target_scale(self):
        return np.any([target.do_scale for target in self.targets])

    def do_change_aspect_ratio(self):
        return np.any([target.fixed_aspect for target in self.targets])

    def width(self):
        return (self.p2-self.p1)[0]

    def height(self):
        return (self.p2-self.p1)[1]

    def size(self):
        return self.p2-self.p1

    def get_trans_matrix(self):
        x, y = self.p1
        w, h = self.size()
        return np.array([[w, 0, x], [0, h, y], [0, 0, 1]], dtype=float)

    def get_inv_trans_matrix(self):
        x, y = self.p1
        w, h = self.size()
        return np.array([[1./w, 0, -x/w], [0, 1./h, -y/h], [0, 0, 1]], dtype=float)

    def transform(self, pos):
        return np.dot(self.get_trans_matrix(), [pos[0], pos[1], 1.0])

    def inv_transform(self, pos):
        return np.dot(self.get_inv_trans_matrix(), [pos[0], pos[1], 1.0])

    def get_pos(self, pos):
        return self.transform(pos)

    def start_move(self):
        self.start_p1 = self.p1.copy()
        self.start_p2 = self.p2.copy()
        self.hide_grabber()

    def end_move(self):
        self.update_grabber()
        self.figure.canvas.draw()

    def addOffset(self, pos, dir, keep_aspect_ratio=True):
        pos = list(pos)
        self.old_inv_transform = self.get_inv_trans_matrix()

        if (keep_aspect_ratio or self.do_change_aspect_ratio()) and not (dir & DIR_X0 and dir & DIR_X1 and dir & DIR_Y0 and dir & DIR_Y1):
            if (dir & DIR_X0 and dir & DIR_Y0) or (dir & DIR_X1 and dir & DIR_Y1):
                dx = pos[1]*self.width()/self.height()
                dy = pos[0]*self.height()/self.width()
                if abs(dx) < abs(dy):
                    pos[0] = dx
                else:
                    pos[1] = dy
            elif (dir & DIR_X0 and dir & DIR_Y1) or (dir & DIR_X1 and dir & DIR_Y0):
                dx = -pos[1]*self.width()/self.height()
                dy = -pos[0]*self.height()/self.width()
                if abs(dx) < abs(dy):
                    pos[0] = dx
                else:
                    pos[1] = dy
            elif dir & DIR_X0 or dir & DIR_X1:
                dy = pos[0]*self.height()/self.width()
                if dir & DIR_X0:
                    self.p1[1] = self.start_p1[1] + dy/2
                    self.p2[1] = self.start_p2[1] - dy/2
                else:
                    self.p1[1] = self.start_p1[1] - dy / 2
                    self.p2[1] = self.start_p2[1] + dy / 2
            elif dir & DIR_Y0 or dir & DIR_Y1:
                dx = pos[1]*self.width()/self.height()
                if dir & DIR_Y0:
                    self.p1[0] = self.start_p1[0] + dx/2
                    self.p2[0] = self.start_p2[0] - dx/2
                else:
                    self.p1[0] = self.start_p1[0] - dx / 2
                    self.p2[0] = self.start_p2[0] + dx / 2

        if dir & DIR_X0:
            self.p1[0] = self.start_p1[0] + pos[0]
        if dir & DIR_X1:
            self.p2[0] = self.start_p2[0] + pos[0]
        if dir & DIR_Y0:
            self.p1[1] = self.start_p1[1] + pos[1]
        if dir & DIR_Y1:
            self.p2[1] = self.start_p2[1] + pos[1]

        transform = np.dot(self.get_trans_matrix(), self.old_inv_transform)
        for target in self.targets:
            self.transform_target(transform, target)

        for rect in self.targets_rects:
            self.transform_target(transform, TargetWrapper(rect))

    def move(self, pos, dir, snaps, keep_aspect_ratio=False, ignore_snaps=False):
        self.addOffset(pos, dir, keep_aspect_ratio)

        if not ignore_snaps:
            offx, offy = snap.checkSnaps(snaps)
            self.addOffset((pos[0]-offx, pos[1]-offy), dir, keep_aspect_ratio)

            offx, offy = snap.checkSnaps(self.snaps)

        snap.checkSnapsActive(snaps)

        self.figure.canvas.draw()

    def apply_transform(self, transform, point):
        point = np.array(point)
        point = np.hstack((point, np.ones((point.shape[0], 1)))).T
        return np.dot(transform, point)[:2].T

    def transform_target(self, transform, target):
        points = target.get_positions()
        points = self.apply_transform(transform, points)
        target.set_positions(points)

    def keyPressEvent(self, event):
        #if not self.selected:
        #    return
        # move last axis in z order
        if event.key == 'pagedown':
            for target in self.targets:
                target.target.set_zorder(target.target.get_zorder() - 1)
            self.figure.canvas.draw()
        if event.key == 'pageup':
            for target in self.targets:
                target.target.set_zorder(target.target.get_zorder() + 1)
            self.figure.canvas.draw()
        if event.key == 'left':
            self.start_move()
            self.addOffset((-10, 0), self.dir)
            self.end_move()
        if event.key == 'right':
            self.start_move()
            self.addOffset((+10, 0), self.dir)
            self.end_move()
        if event.key == 'down':
            self.start_move()
            self.addOffset((0, -10), self.dir)
            self.end_move()
        if event.key == 'up':
            self.start_move()
            self.addOffset((0, +10), self.dir)
            self.end_move()
        if event.key == "escape":
            self.clear_targets()
            self.figure.canvas.draw()


class DragManager:
    selected_element = None
    grab_element = None

    def __init__(self, figure):
        self.figure = figure
        self.figure.figure_dragger = self

        self.figure.canvas.mpl_disconnect(self.figure.canvas.manager.key_press_handler_id)

        self.c3 = self.figure.canvas.mpl_connect('button_release_event', self.button_release_event0)
        self.c2 = self.figure.canvas.mpl_connect('button_press_event', self.button_press_event0)
        self.c4 = self.figure.canvas.mpl_connect('key_press_event', self.key_press_event)

        self.selection = GrabbableRectangleSelection(figure)
        self.figure.selection = GrabbableRectangleSelection(figure)
        self.change_tracker = ChangeTracker(figure)
        self.figure.change_tracker = self.change_tracker

    def make_dragable(self, target):
        if isinstance(target, Text):
            target.set_picker(True)
            target.set_bbox(dict(facecolor="none", edgecolor="none"))

    def get_picked_element(self, event, element=None, picked_element=None, last_selected=None):
        # start with the figure
        if element is None:
            element = self.figure
        finished = False
        # iterate over all children
        for child in sorted(element.get_children(), key=lambda x: x.get_zorder()):
            # check if the element is contained in the event and has an active dragger
            #if child.contains(event)[0] and ((getattr(child, "_draggable", None) and getattr(child, "_draggable",
            #                                                                               None).connected) or isinstance(child, GrabberGeneric) or isinstance(child, GrabbableRectangleSelection)):
            if child.contains(event)[0] and (child.pickable() or isinstance(child, GrabberGeneric)) and not (child.get_label() is not None and child.get_label().startswith("_")):
                # if the element is the last selected, finish the search
                if child == last_selected:
                    return picked_element, True
                # use this element as the current best matching element
                picked_element = child
            # iterate over the children's children
            picked_element, finished = self.get_picked_element(event, child, picked_element, last_selected=last_selected)
            # if the subcall wants to finish, just break the loop
            if finished:
                break
        return picked_element, finished

    def button_release_event0(self, event):
        # release the grabber
        if self.grab_element:
            self.grab_element.button_release_event(event)
            self.grab_element = None
        # or notify the selected element
        elif len(self.selection.targets):
            self.selection.button_release_event(event)

    def button_press_event0(self, event):
        if event.button == 1:
            last = self.selection.targets[-1] if len(self.selection.targets) else None
            contained = np.any([t.target.contains(event)[0] for t in self.selection.targets])

            # recursively iterate over all elements
            picked_element, _ = self.get_picked_element(event, last_selected=last if event.dblclick else None)

            # if the element is a grabber, store it
            if isinstance(picked_element, GrabberGeneric):
                self.grab_element = picked_element
            # if not, we want to keep our selected element, if the click was in the area of the selected element
            elif len(self.selection.targets) == 0 or not contained or event.dblclick:
                self.select_element(picked_element, event)
                contained = True

            # if we have a grabber, notify it
            if self.grab_element:
                self.grab_element.button_press_event(event)
            # if not, notify the selected element
            elif contained:
                self.selection.button_press_event(event)

    def select_element(self, element, event=None):
        print("################## select element", element, self.selection.targets)
        # do nothing if it is already selected
        if element == self.selected_element:
            return
        # if there was was previously selected element, deselect it
        if self.selected_element is not None:
            self.on_deselect(event)
            self.selected_element = None

        # if there is a new element, select it
        if element is not None:
            self.on_select(element, event)
            self.selected_element = element
        self.figure.canvas.draw()
        print("################## select element", element, self.selection.targets)

    def on_deselect(self, event):
        modifier = "shift" in event.key.split("+") if event is not None and event.key is not None else False
        if not modifier:
            self.selection.clear_targets()

    def on_select(self, element, event):
        self.selection.add_target(element)

    def key_press_event(self, event):
        # space: print code to restore current configuration
        if event.key == 'ctrl+s':
            self.figure.change_tracker.save()
        if event.key == "ctrl+z":
            self.figure.change_tracker.backEdit()
        if event.key == "ctrl+y":
            self.figure.change_tracker.forwardEdit()

class GrabberGeneric(GrabFunctions):

    def __init__(self, parent, x, y, dir):
        GrabFunctions.__init__(self, parent, dir)
        self.pos = (x, y)
        self.updatePos()

    def get_xy(self):
        return self.center

    def set_xy(self, xy):
        self.center = xy

    def getPos(self):
        x, y = self.get_xy()
        return self.transform.transform((x, y))

    def updatePos(self):
        self.set_xy(self.parent.get_pos(self.pos))

    def applyOffset(self, pos, event):
        self.set_xy((self.ox+pos[0], self.oy+pos[1]))


class GrabberGenericRound(Ellipse, GrabberGeneric):
    d = 10

    def __init__(self, parent, x, y, dir):
        GrabberGeneric.__init__(self, parent, x, y, dir)
        Ellipse.__init__(self, (0, 0), self.d, self.d, picker=True, figure=parent.figure, edgecolor="k", facecolor="r", zorder=1000, label="grabber")
        self.figure.patches.append(self)
        self.updatePos()


class GrabberGenericRectangle(Rectangle, GrabberGeneric):
    d = 10

    def __init__(self, parent, x, y, dir):
        Rectangle.__init__(self, (0, 0), self.d, self.d, picker=True, figure=parent.figure, edgecolor="k", facecolor="r", zorder=1000, label="grabber")
        GrabberGeneric.__init__(self, parent, x, y, dir)
        self.figure.patches.append(self)
        self.updatePos()

    def get_xy(self):
        xy = Rectangle.get_xy(self)
        return xy[0] + self.d / 2, xy[1] + self.d / 2

    def set_xy(self, xy):
        Rectangle.set_xy(self, (xy[0] - self.d / 2, xy[1] - self.d / 2))


if __name__ == "__main__":
    import matplotlib as mpl

    plt.subplot(221)
    plt.subplot(222)
    plt.subplot(223)

    plt.plot([0, 1], [0, 1])

    #r = mpl.patches.Rectangle([0, 0], width=0.5, height=0.5, picker=True, transform=plt.gcf().transFigure, clip_on=False)
    r = mpl.patches.Rectangle([0, 0], width=0.5, height=0.5, picker=True, figure=plt.gcf(),  clip_on=True)
    #plt.gca().add_patch(r)

    r1 = mpl.patches.Rectangle([0.3, 0.3], width=0.5, height=0.5, picker=True, facecolor="red", transform=plt.gcf().transFigure,
                              clip_on=False, label="red")
    plt.gca().add_patch(r1)
    #print(r1.get_label())
    #die

    #sel.add_target(r)
    #sel.add_target(r1)

    r1 = mpl.patches.Ellipse([0.3, 0.3], width=0.2, height=0.2, picker=True, facecolor="green",
                               transform=plt.gcf().transFigure,
                               clip_on=False, label="green")
    #plt.gca().add_patch(r1)
    #sel.add_target(r1)


    r1 = mpl.patches.Circle([0.3, 0.5], radius=0.2, picker=True, facecolor="magenta",
                               transform=plt.gcf().transFigure,
                               clip_on=False, label="pink")
    plt.gca().add_patch(r1)

    t = plt.text(0.2, 0, "bla\nblubububub", ha="center", zorder=9999, picker=True)
    t.set_bbox(dict(facecolor="none", edgecolor="none"))

    t = plt.text(0.4, 0, "bla\nblubububub", ha="center", zorder=9999, picker=True)
    t.set_bbox(dict(facecolor="none", edgecolor="none"))

    image = np.zeros([100, 20])

    image[:, :] = np.arange(20)
    plt.imshow(image)

    #% start: automatic generated code from pylustrator
    fig = plt.figure(1)
    fig.ax_dict = {ax.get_label(): ax for ax in fig.axes}
    fig.axes[0].set_position([0.125000, 0.571841, 0.352273, 0.350000])
    fig.axes[1].set_position([0.546165, 0.571841, 0.352273, 0.350000])
    fig.axes[2].set_position([0.342187, 0.129600, 0.352273, 0.350000])
    fig.axes[2].texts[0].set_position([0.829059, 0.092050])
    fig.axes[2].texts[1].set_position([0.531734, 0.486551])
    fig.axes[2].patches[0].set_xy([0.367188, 0.166108])
    fig.axes[2].patches[0].set_width(0.500000)
    fig.axes[2].patches[0].set_height(0.500000)
    #% end: automatic generated code from pylustrator
    sel = DragManager(plt.gcf())

    plt.show()