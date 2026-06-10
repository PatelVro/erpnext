# Existing sites get the INV-11A unique index on migrate; fresh installs get
# it from the after_sync hook (canadian_outlet.install).

from canadian_outlet.install import ensure_channel_order_unique_index


def execute():
	ensure_channel_order_unique_index()
