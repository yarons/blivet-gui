# -*- coding: utf-8 -*-

import unittest
from unittest.mock import MagicMock

from blivet.size import Size

from blivetgui.list_partitions import ListPartitions
from blivetgui.gui_utils import locate_ui_file

import os

import gi
gi.require_version("Gtk", "3.0")

from gi.repository import Gtk


@unittest.skipUnless("DISPLAY" in os.environ.keys(), "requires X server")
class ListPartitionsTest(unittest.TestCase):

    def setUp(self):

        _builder = Gtk.Builder()
        _builder.add_from_file(locate_ui_file("blivet-gui.ui"))

        self.blivet_gui = MagicMock(installer_mode=False, builder=_builder)

        self.list_partitions = ListPartitions(self.blivet_gui)

    def test_allow_delete(self):
        # do not allow deleting free space and non-leaf devices
        device = MagicMock(type="free space")
        self.assertFalse(self.list_partitions._allow_delete_device(device))
        device = MagicMock(type="partition", isleaf=False, protected=False)
        self.assertFalse(self.list_partitions._allow_delete_device(device))

        # unformatted leaves can be deleted
        device = MagicMock(type="partition", isleaf=True, format=MagicMock(type=None), protected=False)
        self.assertTrue(self.list_partitions._allow_delete_device(device))

        # only non-active swap can be deleted
        device = MagicMock(type="partition", isleaf=True, format=MagicMock(type="swap", status=True), protected=False)
        self.assertFalse(self.list_partitions._allow_delete_device(device))
        device = MagicMock(type="partition", isleaf=True, format=MagicMock(type="swap", status=False), protected=False)
        self.assertTrue(self.list_partitions._allow_delete_device(device))

        # only unmounted devices can be deleted
        device = MagicMock(type="partition", isleaf=True, format=MagicMock(type="lvmpv", mountable=False), protected=False)
        self.assertTrue(self.list_partitions._allow_delete_device(device))
        device = MagicMock(type="partition", isleaf=True, format=MagicMock(type="ext4", mountable=True, status=False), protected=False)
        self.assertTrue(self.list_partitions._allow_delete_device(device))
        device = MagicMock(type="partition", isleaf=True, format=MagicMock(type="ext4", mountable=True, status=True), protected=False)
        self.assertFalse(self.list_partitions._allow_delete_device(device))

        # protected devices can't be deleteded
        device = MagicMock(type="partition", isleaf=True, protected=True)
        self.assertFalse(self.list_partitions._allow_delete_device(device))

    def test_allow_add(self):
        # do not allow adding on protected devices
        device = MagicMock(type="free space", protected=True)
        self.assertFalse(self.list_partitions._allow_add_device(device))

        # allow adding on free space and btrfs volumes
        device = MagicMock(type="free space", protected=False)
        self.assertTrue(self.list_partitions._allow_add_device(device))
        device = MagicMock(type="btrfs volume", protected=False)
        self.assertTrue(self.list_partitions._allow_add_device(device))

        # allow adding on empty lvmpv
        device = MagicMock(type="partition", protected=False, children=[], format=MagicMock(type="lvmpv"))
        self.assertTrue(self.list_partitions._allow_add_device(device))
        device = MagicMock(type="partition", protected=False, children=[MagicMock()], format=MagicMock(type="lvmpv"))
        self.assertFalse(self.list_partitions._allow_add_device(device))

        # allow adding lvm snapshots
        device = MagicMock(type="lvmlv", protected=False, vg=MagicMock(free_space=Size("1 GiB"), pe_size=Size("4 MiB")))
        self.assertTrue(self.list_partitions._allow_add_device(device))

    def test_add_to_store(self):

        # simple partition -- test if added to store correctly
        device = MagicMock(type="partition", size=Size("1 GiB"), path="/dev/vda1",
                           format=MagicMock(type="ext4", mountable=True, label="aaaaa"))
        device.configure_mock(name="vda1")

        mountpoints = {device.path: "/"}
        self.blivet_gui.client.remote_call.return_value = mountpoints
        it = self.list_partitions._add_to_store(device)
        self.assertEqual(self.list_partitions.partitions_list.get_value(it, 1), device.name)
        self.assertEqual(self.list_partitions.partitions_list.get_value(it, 2), device.type)
        self.assertEqual(self.list_partitions.partitions_list.get_value(it, 3), device.format.type)
        self.assertEqual(self.list_partitions.partitions_list.get_value(it, 4), str(device.size))
        self.assertEqual(self.list_partitions.partitions_list.get_value(it, 5), device.format.label)
        self.assertEqual(self.list_partitions.partitions_list.get_value(it, 6), ", ".join(mountpoints))

        # simple partition with multiple mountpoints
        mountpoints = {device.path: ["/", "/mnt"]}
        self.blivet_gui.client.remote_call.return_value = mountpoints
        self.assertEqual(self.list_partitions.partitions_list.get_value(it, 1), device.name)
        self.assertEqual(self.list_partitions.partitions_list.get_value(it, 6), ", ".join(mountpoints))

        # lvmvg with long name -- name should be elipsized and type should be 'lvm'
        device = MagicMock(type="lvmvg", size=Size("1 GiB"),
                           format=MagicMock(type=None, mountable=False, label=None))
        device.configure_mock(name="".join(["a" for i in range(20)]))

        it = self.list_partitions._add_to_store(device)
        self.assertEqual(self.list_partitions.partitions_list.get_value(it, 1), device.name)
        self.assertEqual(self.list_partitions.partitions_list.get_value(it, 2), "lvm")
        self.assertIsNone(self.list_partitions.partitions_list.get_value(it, 3))
        self.assertEqual(self.list_partitions.partitions_list.get_value(it, 4), str(device.size))
        self.assertEqual(self.list_partitions.partitions_list.get_value(it, 5), "")
        self.assertIsNone(self.list_partitions.partitions_list.get_value(it, 6))

        # child device of previously added device
        device = MagicMock(type="lvmlv", size=Size("1 GiB"),
                           format=MagicMock(type="ext4", mountable=True, label=60 * "a"))
        device.configure_mock(name="aaa")

        self.blivet_gui.client.remote_call.return_value = {}
        child_it = self.list_partitions._add_to_store(device, it)
        # check that 'child_it' is actually child of 'it'
        self.assertEqual(self.list_partitions.partitions_list[self.list_partitions.partitions_list.iter_children(it)][0],
                         self.list_partitions.partitions_list[child_it][0])
        self.assertEqual(self.list_partitions.partitions_list.get_value(child_it, 1), device.name)
        self.assertEqual(self.list_partitions.partitions_list.get_value(child_it, 2), "lvmlv")
        self.assertEqual(self.list_partitions.partitions_list.get_value(child_it, 3), device.format.type)
        self.assertEqual(self.list_partitions.partitions_list.get_value(child_it, 4), str(device.size))
        self.assertEqual(self.list_partitions.partitions_list.get_value(child_it, 5), 15 * "a" + "...")
        self.assertEqual(self.list_partitions.partitions_list.get_value(child_it, 6), "")


if __name__ == "__main__":
    unittest.main()
