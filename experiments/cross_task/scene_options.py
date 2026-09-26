"""Shared scene preparation contract, validated before creating group state."""
import hashlib
import json
import os
import pathlib


def add_arguments(parser):
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--blend', type=pathlib.Path)
    mode.add_argument('--fixture', action='store_true')
    mode.add_argument('--ifc', type=pathlib.Path)
    parser.add_argument('--worktree', type=pathlib.Path)
    parser.add_argument('--prepare-script', type=pathlib.Path)
    parser.add_argument('--bonsai-launcher', type=pathlib.Path, default=
                        pathlib.Path(os.environ.get('CODEX_HOME', str(pathlib.Path.home()/'.codex')))/'skills/bonsai-launcher/scripts/bonsai-launcher.ts')
    parser.add_argument('--task-title')
    parser.add_argument('--prepare-timeout', type=float, default=120)
    parser.add_argument('--blender', type=pathlib.Path, default=pathlib.Path('/Applications/Blender.app/Contents/MacOS/Blender'))


def validate(args):
    def require(ok, message):
        if not ok:raise ValueError(message)
    require(args.blender.is_file(), 'Blender executable missing')
    require(0 < args.prepare_timeout <= 600, 'Preparation timeout must be within 600 seconds')
    for name in ('blend', 'ifc', 'prepare_script'):
        value = getattr(args, name)
        if value:require(value.is_file(), name+' file missing')
    require(not args.prepare_script or args.ifc, '--prepare-script requires --ifc')
    require(not args.worktree or args.ifc, '--worktree requires --ifc')
    if args.ifc:
        require(args.ifc.suffix.lower() in ('.ifc','.ifczip','.ifcxml','.ifcsqlite'), 'Expected IFC file')
        require(args.worktree and args.worktree.is_dir(), 'IFC startup requires the actual --worktree')
        require(args.bonsai_launcher.is_file(), 'Installed Bonsai launcher missing; provide --bonsai-launcher')


def forwarded(args):
    result = ['--blender', str(args.blender.resolve()), '--prepare-timeout', str(args.prepare_timeout)]
    for name in ('blend', 'ifc', 'worktree', 'prepare_script'):
        value = getattr(args, name)
        if value:result += ['--'+name.replace('_','-'), str(value.resolve())]
    if args.fixture:result += ['--fixture']
    if args.ifc:result += ['--bonsai-launcher', str(args.bonsai_launcher.resolve())]
    if args.task_title:result += ['--task-title', args.task_title]
    return result


def ifc_ready(log, path, pid, before_hash):
    # The loader may still be writing its last line while preparation polls.
    rows = [s.rstrip('\r\n') for s in log.read_text(errors='replace').splitlines(keepends=True) if s.endswith('\n')]
    failures = [s for s in rows if s.startswith('TASK_BLENDER_IFC_FAILED ')]
    if failures:raise ValueError('IFC bootstrap failed: '+failures[-1])
    records = [json.loads(s.split(' ',1)[1]) for s in rows if s.startswith('TASK_BLENDER_IFC_READY ')]
    if not records:return None
    record = records[-1]
    if not (record['pid']==pid and pathlib.Path(record['ifc']).resolve()==path.resolve()
            and record['sha256']==before_hash and not record['blend_saved'] and not record['has_blend_warning']
            and hashlib.sha256(path.read_bytes()).hexdigest()==before_hash):
        raise ValueError('IFC bootstrap receipt or source hash mismatch')
    return record
