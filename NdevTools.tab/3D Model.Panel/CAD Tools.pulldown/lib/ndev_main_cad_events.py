"""Revit ExternalEvent dispatch for the modeless CAD mapping window."""
from pyrevit import UI


class CadEventHandler(UI.IExternalEventHandler):
    def __init__(self,window):
        self.window=window
        self.pending=[]

    def request(self,callback,args):
        if self.window._closed:
            return
        start=getattr(self.window,'api_request_started',None)
        if start is not None and start(callback.__name__) is False:
            return
        self.pending.append((callback,args))
        try:
            state=self.window._external_event.Raise()
        except Exception:
            self.pending=[]
            self.finish(cancelled=True)
            raise
        if state==UI.ExternalEventRequest.Denied:
            self.pending=[]
            self.window.status.Text='Revit refused the request. Finish the current command and try again.'
            self.finish(cancelled=True)

    def finish(self,cancelled=False):
        finish=getattr(self.window,'api_request_finished',None)
        if finish is not None:
            finish(cancelled)

    def Execute(self,uiapp):
        window=self.window
        pending,self.pending=self.pending,[]
        if window._closed:
            return
        window._api_active=True
        cancelled=False
        try:
            active=uiapp.ActiveUIDocument
            if not window.doc.IsValidObject or active is None or active.Document!=window.doc:
                cancelled=True
                window.status.Text='Activate the project used by this mapping window before scanning or placing.'
                return
            for callback,args in pending:
                try:
                    callback(window,*args)
                except Exception as error:
                    cancelled=True
                    window.status.Text='CAD request stopped: '+str(error)
        finally:
            window._api_active=False
            self.finish(cancelled)

    def GetName(self):
        return 'NdevTools CAD mapping actions'


def api_callback(callback):
    def dispatch(self,*args):
        if self._closed:
            return
        if callback.__name__ in ('scan_setting_changed','filter_changed') and self._formatting:
            return
        if self._ready and args:
            sender=args[0]
            if callback.__name__=='scan_setting_changed' and sender is not None:
                self._measure_cache.pop(sender.Name,None)
            elif callback.__name__=='filter_changed' and sender==self.cutoff_width:
                self._measure_cache.pop('cutoff_width',None)
        if callback.__name__=='auto_scan':
            self._scan_timer.Stop()
        if self._api_active:
            return callback(self,*args)
        self._event_handler.request(callback,args)
    return dispatch
