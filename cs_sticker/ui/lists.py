# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Sticker list with search / collection / finish filtering."""

import bpy

from ..library import finishes as F
from ..library import registry


class CSSTICKER_UL_stickers(bpy.types.UIList):
    """Library entries. The list data is already filtered by the search
    fields above it (see registry.sync_items), so no filter_items here."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index=0, flt_flag=0):
        sticker = registry.get_catalog().get(item.sticker_id)
        icon_id = registry.preview_icon(sticker) if sticker else 0
        row = layout.row(align=True)
        if icon_id:
            row.label(text=item.name, icon_value=icon_id)
        else:
            row.label(text=item.name, icon="IMAGE_DATA")
        if item.has_missing:
            row.label(text="", icon="ERROR")
        finish = F.FINISHES.get(item.finish)
        row.label(text=finish.label if finish else item.finish)

    def draw_filter(self, context, layout):
        # Filters live in the panel (shared with the search field).
        pass



classes = (CSSTICKER_UL_stickers,)
