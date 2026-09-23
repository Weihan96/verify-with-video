"""Task-bound Blender input receiver with an optional disposable UI fixture. Run with --enable-event-simulate.

Commands are JSON files in a private run directory, consumed on Blender's main
thread. UI actions use window events; direct assignments only prepare fixtures.
The coordinator releases the preparation lease after fixed-session admission.
"""
import bpy
import blf
import json
import os
import pathlib
import sys
import time

args = sys.argv[sys.argv.index('--') + 1:]
run = pathlib.Path(args[args.index('--probe-dir') + 1]).resolve()
label = args[args.index('--probe-label') + 1]
preserve_scene = '--preserve-scene' in args
run.mkdir(parents=True, exist_ok=True)
pending = []
cursor = [100, 100]
sequence = 0
last_state = None
drained = True
held = {}
control_ack = None
input_epoch = 0
drain_barrier = None
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import access
participant_path = run / 'participant.json'
participant, _, _ = access.participant(participant_path, 'launch')
assert participant['thread_id'] == os.environ['CODEX_THREAD_ID']
bpy.app.use_userpref_skip_save_on_exit = True
bpy.context.preferences.view.filebrowser_display_type = 'SCREEN'
bpy.context.preferences.view.render_display_type = 'AREA'
bpy.context.preferences.inputs.use_mouse_continuous = False



def write(name, data):
    tmp = run / (name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    tmp.replace(run / name)


def log(data):
    with (run / 'events.jsonl').open('a') as f:
        f.write(json.dumps(dict(time=time.time(), pid=os.getpid(), **data)) + '\n')


class ProbeProperties(bpy.types.PropertyGroup):
    text: bpy.props.StringProperty(name='Text', default='ready')
    value: bpy.props.FloatProperty(name='Value', default=1.0)
    enabled: bpy.props.BoolProperty(name='Enabled', default=False)
    clicks: bpy.props.IntProperty(default=0)


class PROBE_OT_increment(bpy.types.Operator):
    bl_idname = 'probe.increment'
    bl_label = 'Increment'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.input_probe.clicks += 1
        log({'event': 'button_executed', 'clicks': context.scene.input_probe.clicks})
        return {'FINISHED'}


class PROBE_OT_popup(bpy.types.Operator):
    bl_idname = 'probe.popup'
    bl_label = 'Probe Popup'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=260)

    def draw(self, context):
        self.layout.label(text='Popup in instance ' + label)
        self.layout.prop(context.scene.input_probe, 'text')

    def execute(self, context):
        log({'event': 'popup_confirmed'})
        return {'FINISHED'}


class PROBE_PT_panel(bpy.types.Panel):
    bl_label = 'Input isolation ' + label
    bl_idname = 'PROBE_PT_input'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Item'
    bl_order = -1000

    def draw(self, context):
        p = context.scene.input_probe
        self.layout.label(text='Instance ' + label + ' | PID ' + str(os.getpid()))
        self.layout.prop(p, 'text')
        self.layout.prop(p, 'value')
        self.layout.prop(p, 'enabled')
        self.layout.operator('probe.increment', text='Increment: ' + str(p.clicks))
        self.layout.operator('probe.popup')


if not preserve_scene:
    for cls in [ProbeProperties, PROBE_OT_increment, PROBE_OT_popup, PROBE_PT_panel]:
        bpy.utils.register_class(cls)
    bpy.types.Scene.input_probe = bpy.props.PointerProperty(type=ProbeProperties)
    bpy.context.scene.name = 'Input probe ' + label
    bpy.context.scene.input_probe.text = 'ready-' + label


# Release candidate imported directly; fixture UI is test preparation only.
import importlib.util
candidate = pathlib.Path(__file__).resolve().parents[2] / 'scripts/blender_cursor.py'
spec = importlib.util.spec_from_file_location('release_cursor', candidate)
marker_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(marker_module)
marker = marker_module.enable(bpy.context.window, label)


def state():
    p = bpy.context.scene.input_probe if not preserve_scene else None
    return dict(pid=os.getpid(), label=label, text=p.text if p else None, value=p.value if p else None,
                enabled=p.enabled if p else None, clicks=p.clicks if p else None, filepath=bpy.data.filepath,
                scene_mode='preserve' if preserve_scene else 'fixture',
                objects=[dict(name=o.name,location=list(o.location),rotation=list(o.rotation_euler),scale=list(o.scale)) for o in bpy.context.selected_objects],
                thread_id=os.environ['CODEX_THREAD_ID'], drained=drained, control_ack=control_ack,input_epoch=input_epoch,held=list(held),
                units=dict(system=bpy.context.scene.unit_settings.system,length=bpy.context.scene.unit_settings.length_unit),
                profile=dict(filebrowser=bpy.context.preferences.view.filebrowser_display_type,continuous=bpy.context.preferences.inputs.use_mouse_continuous,skip_save=bpy.app.use_userpref_skip_save_on_exit),
                windows=[dict(pointer=str(w.as_pointer()), width=w.width, height=w.height,
                              areas=[dict(type=a.type, x=a.x, y=a.y, width=a.width, height=a.height,
                                          perspective=a.spaces.active.region_3d.view_perspective
                                          if a.type == 'VIEW_3D' else None,
                                          view_rotation=list(a.spaces.active.region_3d.view_rotation) if a.type == 'VIEW_3D' else None,
                                          view_distance=a.spaces.active.region_3d.view_distance if a.type == 'VIEW_3D' else None,
                                          regions=[dict(type=r.type, x=r.x, y=r.y, width=r.width, height=r.height)
                                                   for r in a.regions]) for a in w.screen.areas])
                         for w in bpy.context.window_manager.windows])


def validate_command(cmd, operation='simulate'):
    if cmd.get('thread_id') != os.environ['CODEX_THREAD_ID'] or cmd.get('token') != participant['token']:
        raise ValueError('Wrong task or participant capability')
    g, m = access.authorize(participant['group'],participant['token'],os.environ['CODEX_THREAD_ID'],operation)
    if operation == 'simulate':
        if drained:raise ValueError('Input is drained')
        if cmd.get('epoch')!=input_epoch:raise ValueError('Stale input epoch')
        session=json.loads((run/'session.json').read_text())
        if session['pid'] != os.getpid() or session['thread_id'] != os.environ['CODEX_THREAD_ID']:
            raise ValueError('Worker/session identity mismatch')
        access.recording(session)
    return m


def release_local():
    # Cleanup is local simulated input only, never a system/HID reset.
    w=next((w for w in bpy.context.window_manager.windows if str(w.as_pointer())==bound_window),None)
    if w:
        for name in list(held):w.event_simulate(type=name,value='RELEASE',x=cursor[0],y=cursor[1])
        w.event_simulate(type='ESC',value='PRESS',x=cursor[0],y=cursor[1])
        w.event_simulate(type='ESC',value='RELEASE',x=cursor[0],y=cursor[1])
    held.clear()


def tick():
    global sequence, last_state, marker, drained, control_ack,input_epoch,drain_barrier
    try:
        if drain_barrier:
            drain_barrier['ticks']+=1
            if drain_barrier['ticks']>=2 and time.time()-drain_barrier['time']>=.12:
                control_ack=drain_barrier['id'];log(dict(event='input_drained',request=control_ack,epoch=input_epoch,held=list(held),pending=len(pending)));drain_barrier=None
        control_file=run/'input-control.json'
        if control_file.exists():
            cmd=json.loads(control_file.read_text());control_file.unlink()
            validate_command(cmd,'record-control')
            if cmd['action']=='drain':
                input_epoch+=1;pending.clear();drained=True
                for old in run.glob('command-*.json'):old.rename(old.with_suffix('.cancelled'))
                release_local();drain_barrier=dict(id=cmd['id'],ticks=0,time=time.time())
            elif cmd['action']=='resume':
                if drain_barrier:raise ValueError('Drain barrier not complete')
                access.recording(json.loads((run/'session.json').read_text()));drained=False
                control_ack=cmd['id']
            else:raise ValueError('Unknown input lifecycle action')
            log(dict(event='input_lifecycle',action=cmd['action'],request=cmd['id']))
        for path in sorted(run.glob('command-*.json')):
            cmd = json.loads(path.read_text())
            path.rename(path.with_suffix('.accepted'))
            validate_command(cmd)
            if not isinstance(cmd['events'],list) or not 0<len(cmd['events'])<=1000:raise ValueError('Unbounded event batch')
            if cmd.get('start_at',0)>time.time()+120 or sum(e.get('delay',.12) for e in cmd['events'])>120 or any(not 0<=e.get('delay',.12)<=10 for e in cmd['events']):raise ValueError('Unbounded event schedule')
            start = max(time.time(), cmd.get('start_at', 0))
            for event in cmd['events']:
                start += event.get('delay', 0.12)
                pending.append((start, cmd, event))
            pending.sort(key=lambda item:item[0])
        now = time.time()
        while pending and pending[0][0] <= now:
            _, command, spec = pending.pop(0)
            member=validate_command(command)
            if spec['window']!=bound_window or spec['window']!=member['blender_window']:
                raise ValueError('Unbound Blender window')
            command_id=command['id']
            w = next(w for w in bpy.context.window_manager.windows
                     if str(w.as_pointer()) == spec['window'])
            kwargs = {k: v for k, v in spec.items() if k not in ('delay', 'window')}
            kwargs.setdefault('x', cursor[0])
            kwargs.setdefault('y', cursor[1])
            if len(bpy.context.window_manager.windows)!=1:raise ValueError('Unexpected extra Blender window')
            if kwargs['type'] not in ('A','C','V','RET','ESC','MOUSEMOVE','LEFTMOUSE','MIDDLEMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE') or kwargs.get('oskey'):
                raise ValueError('Event outside scoped experiment')
            w.event_simulate(**kwargs)
            if kwargs['value']=='PRESS':held[kwargs['type']]=True
            elif kwargs['value']=='RELEASE':held.pop(kwargs['type'],None)
            cursor[:] = [kwargs['x'], kwargs['y']]
            if not marker.closed:
                marker.update(w, *cursor)
            sequence += 1
            log({'event': 'injected', 'command_id': command_id, 'sequence': sequence, 'input': kwargs})
            for area in w.screen.areas:
                area.tag_redraw()
        current = state()
        if current != last_state:
            log({'event': 'state_changed', 'state': current})
            last_state = current
        write('state.json', dict(time=time.time(), sequence=sequence, pending=len(pending), **current))
    except Exception as e:
        log({'event': 'error', 'error': repr(e)})
        pending.clear();release_local();drained=True
    return 0.03


def prepare():
    global bound_window
    bound_window=str(bpy.context.window.as_pointer())
    if not preserve_scene:
        # A visible disposable cube makes orbit results inspectable in real footage.
        mesh=bpy.data.meshes.new('Parallel probe '+label)
        mesh.from_pydata([(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),(1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)],[],[(0,4,6,2),(1,3,7,5),(0,1,5,4),(2,6,7,3),(0,2,3,1),(4,5,7,6)])
        obj=bpy.data.objects.new('Parallel probe '+label,mesh);bpy.context.scene.collection.objects.link(obj)
        for other in bpy.context.selected_objects:other.select_set(False)
        obj.select_set(True);bpy.context.view_layer.objects.active=obj
    for w in bpy.context.window_manager.windows:
        for area in w.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'PERSP'
                if not preserve_scene:
                    area.spaces.active.region_3d.view_distance = 7
                    area.spaces.active.region_3d.view_location = (0,0,0)
                if not preserve_scene:
                    area.spaces.active.show_region_ui = True
                for region in ([] if preserve_scene else area.regions):
                    if region.type == 'UI':
                        try:
                            region.active_panel_category = 'Item'
                        except Exception:
                            pass
    # Fixture saving is preparation, not claimed as an input/save test.
    if not preserve_scene:
        bpy.ops.wm.save_as_mainfile(filepath=str(run / ('fixture-' + label + '.blend')))
    log({'event': 'prepared', 'state': state(), 'blender': bpy.app.version_string})
    bpy.app.timers.register(tick, persistent=True)
    return None


bpy.app.timers.register(prepare, first_interval=2.0)
