"""FCPXML via the upstream OTIO adapter, upgraded to current media references.

The adapter owns the document, resources, sequence, spine and lane serialization.
See docs/exporter-decision.md before changing its pinned version or these hooks.
"""

from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

import opentimelineio as otio
from otio_fcpx_xml_adapter.fcpx_xml import FcpxOtio

from .models import Timeline
from .otio_builder import build_otio
from .report import write_new


def xml_time(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}s"


def seconds(value: str | None) -> Fraction:
    return Fraction((value or "0s").removesuffix("s"))


class FujiAdapter(FcpxOtio):
    def __init__(self, timeline, fps: Fraction, width: int, height: int):
        self.fps, self.width, self.height = fps, width, height
        self.formats = {}
        super().__init__(timeline)

    def _find_or_create_format_from(self, item):
        info = item.media_reference.metadata.get("fuji", {}) if isinstance(item, otio.schema.Clip) else {}
        width, height = info.get("width", 0) or self.width, info.get("height", 0) or self.height
        still = info.get("kind") == "photo"
        rate = Fraction(info.get("fps", self.fps))
        key = (width, height, still, rate if not still else None)
        if key not in self.formats:
            attributes = {"id": self._resource_id_generator(), "width": str(width), "height": str(height)}
            if not still:
                attributes["frameDuration"] = xml_time(1 / rate)
                # Explicit preset used by the real Mac/FCP import checkpoint.
                if not info:
                    attributes["colorSpace"] = "1-1-1 (Rec. 709)"
                if (width, height, rate) == (1920, 1080, Fraction(30)):
                    attributes["name"] = "FFVideoFormat1080p30"
            self.formats[key] = ET.SubElement(self.resource_element, "format", attributes)
        return self.formats[key]

    def _asset_by_path(self, path):
        # Avoid upstream XPath interpolation for filenames containing quotes.
        return next((e for e in self.resource_element.findall("asset") if e.get("src") == path), None)

    def _asset_clip_by_name(self, name):
        return next((e for e in self.event_resource.findall("asset-clip") if e.get("name") == name), None)

    def _create_asset_clip_element(self, clip, format_element, resource_id):
        # The project already references every resource. Do not also generate
        # browser clips (in particular, zero-length browser clips for JPEGs).
        return None

    def _find_asset_duration(self, item):
        info = item.media_reference.metadata["fuji"]
        # The resource for a still has zero duration; its edit is independently timed.
        return xml_time(Fraction(info["duration"]))

    def _find_asset_start(self, item):
        return xml_time(Fraction(item.media_reference.metadata["fuji"]["source_start"]))

    def _add_asset(self, clip, compound_only=False):
        resource_id = super()._add_asset(clip, compound_only)
        info = clip.media_reference.metadata["fuji"]
        asset = self._asset_by_id(resource_id)
        if info["kind"] == "sound":
            asset.attrib.pop("format", None)
        if info["channels"]:
            asset.set("hasAudio", "1")
            asset.set("audioSources", "1")
            asset.set("audioChannels", str(info["channels"]))
            asset.set("audioRate", str(info["sample_rate"]))
        return resource_id

    def _element_for_clip(self, item, asset_id, duration, lane):
        info = item.media_reference.metadata["fuji"]
        timing = item.metadata["fuji"]
        attributes = {"name": item.name, "offset": xml_time(Fraction(timing["offset"])),
                      "duration": xml_time(Fraction(timing["duration"])),
                      "start": xml_time(Fraction(info["source_start"]))}
        if info["kind"] in {"video", "sound"}:
            # asset-clip retains the video's original audio as well as its picture.
            element = ET.Element("asset-clip", {**attributes, "ref": asset_id})
            if info["kind"] == "sound":
                element.set("audioRole", "effects.shutter")
            return element
        element = super()._element_for_clip(item, asset_id, duration, lane)
        element.attrib.update(attributes)
        element.find("video").set("duration", attributes["duration"])
        return element

    def _find_parent_element(self, spine, trimmed_range, format_id):
        position = Fraction(str(trimmed_range.value)) / Fraction(str(trimmed_range.rate))
        # All attached starts are project-frame aligned. Recover that exact
        # frame after OTIO's floating-point track accumulation, notably at cuts.
        position = round(position * self.fps) / self.fps
        for item in spine:
            start = seconds(item.get("offset"))
            if start <= position < start + seconds(item.get("duration")):
                return item
        raise ValueError("Não foi possível conectar um clip à storyline principal.")

    def _offset_based_on_parent(self, child, parent, default_format_id):
        value = seconds(child.get("offset")) - seconds(parent.get("offset")) + seconds(parent.get("start"))
        value = round(value * self.fps) / self.fps
        # Upstream expects RationalTime here. A high integral rate avoids its
        # 'int(value)==0' shortcut wiping sub-frame positive offsets.
        return otio.opentime.RationalTime(float(value * 1_000_000_000), 1_000_000_000)

    @staticmethod
    def _calculate_rational_number(duration, rate):
        return xml_time((Fraction(str(duration)) / Fraction(str(rate))).limit_denominator(1_000_000_000))


def render_fcpxml(plan: Timeline, fps: Fraction = Fraction(30),
                  width: int | None = None, height: int | None = None,
                  target: str = "final-cut") -> tuple[str, list[str]]:
    if bool(width) != bool(height) or (width is not None and (width <= 0 or height <= 0)):
        raise ValueError("Informe largura e altura positivas juntas.")
    if target not in {"final-cut", "resolve"}:
        raise ValueError("Editor de destino inválido; use final-cut ou resolve.")
    timeline, notes = build_otio(plan, fps)
    first = plan.videos[0].media
    adapter = FujiAdapter(timeline, fps, width or first.width, height or first.height)
    xml = adapter.to_xml()
    root = ET.fromstring(xml)
    # Sanity checks are not a substitute for Apple's DTD or Final Cut import.
    ids = [e.get("id") for e in root.findall("./resources/*")]
    if len(ids) != len(set(ids)) or any(e.get("ref") not in ids for e in root.iter() if e.get("ref")):
        raise ValueError("Referências inconsistentes no FCPXML.")
    for project in root.findall("./project"):
        if not project.get("uid"):
            project.attrib.pop("uid", None)
    for seq in root.findall("./project/sequence"):
        seq.set("tcStart", "0s")
        seq.set("audioLayout", "stereo")
        seq.set("audioRate", "48k")
    root.set("version", "1.10" if target == "resolve" else "1.14")
    for asset in root.findall("./resources/asset"):
        source = asset.attrib.pop("src")
        ET.SubElement(asset, "media-rep", {"kind": "original-media", "src": source})
        if asset.get("hasVideo") == "1":
            asset.set("videoSources", "1")
    if target == "resolve":
        library = ET.Element("library")
        event = ET.SubElement(library, "event", {"name": plan.name})
        for project in list(root.findall("project")):
            root.remove(project)
            event.append(project)
        root.append(library)
        notes.append("DaVinci Resolve: FCPXML 1.10 experimental; confirme mídia, áudio e sincronismo após importar a timeline.")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + ET.tostring(root, encoding="unicode")
    return xml, notes


def export_fcpxml(plan: Timeline, output: Path, **options) -> list[str]:
    xml, notes = render_fcpxml(plan, **options)
    write_new(output, xml, ".fcpxml")
    return notes
