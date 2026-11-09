"""Cooperative cancellation shared by discovery, readers and desktop workers."""
class Cancelled(Exception):
    pass


def check_cancel(event):
    if event is not None and event.is_set():
        raise Cancelled('Operação cancelada.')
