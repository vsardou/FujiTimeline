"""Frozen macOS entry point; --self-test exercises the installed bundle."""
import sys
from pathlib import Path

if '--self-test' in sys.argv:
    import json, subprocess, tkinter
    import opentimelineio
    from fujitimeline.desktop import find_tool
    from fujitimeline.demo import demo_timeline
    from fujitimeline.export_fcpxml import render_fcpxml
    from fujitimeline.metadata import MetadataReader
    tk = tkinter.Tk(); tk.withdraw(); tk.update(); tk.destroy()
    results = {}
    for name, flag in [('ffprobe','-version'), ('exiftool','-ver')]:
        tool = find_tool(name)
        results[name] = subprocess.check_output([tool,flag],text=True).splitlines()[0]
        assert str(Path(sys._MEIPASS)) in tool
    for target in ('final-cut', 'resolve'):
        xml, _ = render_fcpxml(demo_timeline(),target=target)
        assert '<sequence' in xml
    if '--video' in sys.argv:
        video=Path(sys.argv[sys.argv.index('--video')+1])
        reader=MetadataReader(find_tool('ffprobe'),find_tool('exiftool'))
        results['video']=str(reader.video(video).source_start)
    if '--photo' in sys.argv:
        photo=Path(sys.argv[sys.argv.index('--photo')+1])
        reader=MetadataReader(find_tool('ffprobe'),find_tool('exiftool'))
        results['photo']=reader.photos((photo,))[0].captured.raw
    Path(sys.argv[sys.argv.index('--self-test')+1]).write_text(json.dumps(results,indent=2))
else:
    from fujitimeline.gui import main
    main()
