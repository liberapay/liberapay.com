from functools import reduce
from importlib import import_module
import os
import sys
from tempfile import NamedTemporaryFile
import tokenize
import warnings

from aspen.simplates.pagination import escape, parse_specline, split
import coverage


__version__ = '0.1'


def import_object(path):
    names = path.split('.')
    module = None
    import_error = None
    for i in range(len(names) - 1, 0, -1):
        module_path, object_path = '.'.join(names[:i]), names[i:]
        if module_path in sys.modules:
            module = sys.modules[module_path]
        else:
            try:
                module = import_module(module_path)
            except ImportError as e:
                if import_error is None:
                    import_error = e
            else:
                break
    if module is None and import_error is not None:
        raise import_error
    return reduce(getattr, object_path, module)


class FilePage:

    __slots__ = (
        'start_line', 'end_line', 'content', 'is_python', 'tracer', 'temp_file', 'reporter',
    )

    def __init__(
        self, start_line, content, is_python, tracer, temp_file, reporter,
    ):
        self.start_line = start_line
        self.end_line = start_line + max(content.count('\n') - 1, 0)
        self.content = content
        self.is_python = is_python
        self.tracer = tracer
        self.temp_file = temp_file
        self.reporter = reporter


class MultiTracer(coverage.plugin.FileTracer):
    """A generic combiner of multiple tracers, for mixed-mode files.
    """

    def __init__(self, filename, pages):
        self.filename = filename
        custom_tracers = []
        python_ranges = []
        prev_page = None
        pages.sort(key=lambda page: page.start_line)
        for page in pages:
            if page.content:
                tracer = page.tracer
                if tracer:
                    tracer.start_line = page.start_line
                    tracer.end_line = page.end_line
                    custom_tracers.append(tracer)
                elif page.is_python:
                    if python_ranges and python_ranges[-1][1] == prev_page.end_line:
                        # Merge consecutive ranges to slightly improve performance
                        python_ranges[-1] = (python_ranges[-1][0], page.end_line)
                    else:
                        python_ranges.append((page.start_line, page.end_line))
            prev_page = page
        self.python_ranges = python_ranges
        self.custom_tracers = custom_tracers

    def source_filename(self):
        return self.filename

    def line_number_range(self, frame):
        frame_line = frame.f_lineno
        custom_matches = []
        out_of_bounds = []
        for tracer in self.custom_tracers:
            try:
                start_line, end_line = tracer.line_number_range(frame)
            except Exception as e:
                warnings.warn(
                    f"{tracer.__class__.__name__}.line_number_range() raised an "
                    f"exception instead of failing gracefully: {e!r}"
                )
            else:
                if start_line == -1 and end_line == -1:
                    continue
                if start_line < tracer.start_line or end_line > tracer.end_line:
                    out_of_bounds.append(tracer)
                    continue
                custom_matches.append((start_line, end_line))
        if custom_matches:
            if len(custom_matches) == 1:
                return custom_matches[0]
            else:
                warnings.warn(
                    f"got conflicting line number ranges for line {frame_line} "
                    f"of file {frame.f_code.co_filename!r}: {custom_matches}"
                )
        else:
            for range_start, range_end in self.python_ranges:
                if frame_line >= range_start and frame_line <= range_end:
                    return frame_line, frame_line
        for tracer in out_of_bounds:
            warnings.warn(
                f"{tracer.__class__.__name__}.line_number_range() "
                f"returned an out of bounds range "
                f"in file {frame.f_code.co_filename}"
            )
        return -1, -1


class MultiReporter(coverage.plugin.FileReporter):
    """A generic combiner of multiple reporters, for mixed-mode files.
    """

    def __init__(self, filename, pages):
        super().__init__(filename)
        pages.sort(key=lambda page: page.start_line)
        self.pages = pages

    def lines(self):
        line_numbers = set()
        for page in self.pages:
            if page.reporter:
                page_lines = page.reporter.lines()
                if not page_lines:
                    continue
                out_of_bounds = (
                    min(page_lines) < page.start_line or
                    max(page_lines) > page.end_line
                )
                if out_of_bounds:
                    warnings.warn(
                        f"{page.reporter.__class__.__name__}.lines() "
                        f"returned out of bounds numbers"
                    )
                else:
                    line_numbers.update(page_lines)
                    continue
            for i, line in enumerate(page.content.splitlines()):
                if line:
                    line_numbers.add(page.start_line + i)
        return line_numbers

    def excluded_lines(self):
        line_numbers = set()
        for page in self.pages:
            if page.reporter:
                page_lines = page.reporter.excluded_lines()
                if not page_lines:
                    continue
                out_of_bounds = (
                    min(page_lines) < page.start_line or
                    max(page_lines) > page.end_line
                )
                if out_of_bounds:
                    warnings.warn(
                        f"{page.reporter.__class__.__name__}.excluded_lines() "
                        f"returned out of bounds numbers"
                    )
                else:
                    line_numbers.update(page_lines)
                    continue
            for i, line in enumerate(page.content.splitlines()):
                if line:
                    line_numbers.add(page.start_line + i)
        return line_numbers

    def translate_lines(self, lines):
        def translate_page_lines(page, page_lines):
            if page.reporter:
                try:
                    translated_page_lines = page.reporter.translate_lines(page_lines)
                except Exception as e:
                    warnings.warn(
                        f"{page.reporter.__class__.__name__}.translate_lines() "
                        f"raised an exception: {e!r}"
                    )
                    return page_lines
                if translated_page_lines:
                    out_of_bounds = (
                        min(translated_page_lines) < page.start_line or
                        max(translated_page_lines) > page.end_line
                    )
                    if out_of_bounds:
                        warnings.warn(
                            f"{page.reporter.__class__.__name__}.translate_lines() "
                            f"returned out of bounds numbers "
                            f"({min(translated_page_lines)} < {page.start_line} or "
                            f"{max(translated_page_lines)} > {page.end_line}) "
                            f"for file {self.filename}"
                        )
                    elif len(translated_page_lines) > len(page_lines):
                        warnings.warn(
                            f"{page.reporter.__class__.__name__}.translate_lines() "
                            f"returned a greater number of lines "
                            f"({len(translated_page_lines)} > {len(page_lines)}) "
                            f"for file {self.filename}"
                        )
                    else:
                        return translated_page_lines
            return page_lines

        try:
            translated_lines = set()
            page_lines = []
            pages_iter = iter(self.pages)
            page = next(pages_iter)
            page_start = page.start_line
            page_end = page.end_line
            for line_number in sorted(lines):
                while line_number > page_end:
                    if page_lines:
                        translated_lines.update(translate_page_lines(page, page_lines))
                        page_lines.clear()
                    page = next(pages_iter, None)
                    if page:
                        page_start, page_end = page.start_line, page.end_line
                    else:
                        page_start, page_end = -1, float('inf')
                if line_number >= page_start:
                    page_lines.append(line_number)
            if page_lines:
                if page:
                    translated_lines.update(translate_page_lines(page, page_lines))
                else:
                    last_page_end = self.pages[-1].end_line
                    warnings.warn(f"got out of bounds line numbers: {page_lines} > {last_page_end}")
            return translated_lines
        except Exception as e:
            warnings.warn(f"exception in {self.__class__.__name__}.translate_lines(): {e!r}")
            return set(lines)

    def arcs(self):
        r = set()
        for page in self.pages:
            if page.reporter:
                r.update(page.reporter.arcs())
        return r

    def no_branch_lines(self):
        r = set()
        for page in self.pages:
            if page.reporter:
                r.update(page.reporter.no_branch_lines())
        return r

    def translate_arcs(self, arcs):
        def translate_page_arcs(page, page_arcs):
            if page.reporter:
                try:
                    translated_page_arcs = page.reporter.translate_arcs(page_arcs)
                except Exception as e:
                    warnings.warn(
                        f"{page.reporter.__class__.__name__}.translate_arcs() "
                        f"raised an exception: {e!r}"
                    )
                    return page_arcs
                if translated_page_arcs:
                    min_arc_start = min(abs(t[0]) for t in translated_page_arcs)
                    max_arc_end = max(abs(t[1]) for t in translated_page_arcs)
                    out_of_bounds = (
                        min_arc_start < page.start_line or
                        max_arc_end > page.end_line
                    )
                    if out_of_bounds:
                        warnings.warn(
                            f"{page.reporter.__class__.__name__}.translate_arcs() "
                            f"returned out of bounds numbers: "
                            f"{min_arc_start} < {page.start_line} or "
                            f"{max_arc_end} > {page.end_line}"
                        )
                    elif len(translated_page_arcs) > len(page_arcs):
                        warnings.warn(
                            f"{page.reporter.__class__.__name__}.translate_arcs() "
                            f"returned a greater number of arcs: "
                            f"{len(translated_page_arcs)} > {len(page_arcs)}"
                        )
                    else:
                        return translated_page_arcs
            return page_arcs

        try:
            translated_arcs = set()
            page_arcs = []
            pages_iter = iter(self.pages)
            page = next(pages_iter)
            page_start = page.start_line
            page_end = page.end_line
            for arc_start, arc_end in sorted(arcs, key=lambda arc: abs(arc[0])):
                while abs(arc_start) > page_end:
                    if page_arcs:
                        translated_arcs.update(translate_page_arcs(page, page_arcs))
                        page_arcs.clear()
                    page = next(pages_iter, None)
                    if page:
                        page_start, page_end = page.start_line, page.end_line
                    else:
                        page_start, page_end = -1, float('inf')
                if abs(arc_end) > page_end:
                    # This arc is between different pages
                    translated_arcs.add((arc_start, arc_end))
                elif abs(arc_start) >= page_start:
                    page_arcs.append((arc_start, arc_end))
            if page_arcs:
                if page:
                    translated_arcs.update(translate_page_arcs(page, page_arcs))
                else:
                    last_page_end = self.pages[-1].end_line
                    warnings.warn(
                        f"got out of bounds line numbers for file {self.filename}: "
                        f"{page_arcs} > {last_page_end}"
                    )
            return translated_arcs
        except Exception as e:
            warnings.warn(f"exception in {self.__class__.__name__}.translate_arcs(): {e!r}")
            return set(arcs)

    def missing_arc_description(self, start, end, executed_arcs=None):
        for page in self.pages:
            if end <= page.end_line and start >= page.start_line:
                reporter = page.reporter or super()
                return reporter.missing_arc_description(start, end, executed_arcs)
        return super().missing_arc_description(start, end, executed_arcs)

    def should_be_python(self):
        # If one of the reporters is based on the python parser, then we assume
        # that the corresponding page is supposed to contain valid python code,
        # and that parsing failures shouldn't be ignored.
        return True

    def source_token_lines(self):
        source_lines = self.source().splitlines()
        lines = []
        for page_id, page in enumerate(self.pages):
            # First, add the gap lines before the page
            gap_start = self.pages[page_id - 1].end_line + 1 if page_id > 0 else 1
            for i in range(gap_start, page.start_line):
                lines.append([('txt', source_lines[i - 1])])
            # Then, add the page's lines
            page_start = page.start_line - 1
            page_end = page.end_line - 1
            if page.reporter:
                page_lines = list(page.reporter.source_token_lines())
                if len(page_lines) > page_end:
                    lines.extend(page_lines[page_start:page_end+1])
                    continue
                else:
                    warnings.warn(
                        f"{page.reporter.__class__.__name__}.source_token_lines() "
                        f"returned an incorrect number of lines"
                    )
            for i in range(page_start, min(page_end + 1, len(source_lines))):
                lines.append([('txt', source_lines[i])])
        if len(lines) != len(source_lines):
            warnings.warn(
                f"incorrect number of lines ({len(lines)} != {len(source_lines)}) "
                f"for file {self.filename}"
            )
            lines = [[('txt', line)] for line in source_lines]
        return lines


def attach_coverage_plugins_to_renderer_factories():
    """TODO
    """
    try:
        import aspen_jinja2_renderer
        import jinja2_coverage
    except ImportError:
        pass
    else:
        if jinja2_coverage.plugin:
            aspen_jinja2_renderer.Factory.coverage_plugin = jinja2_coverage.plugin
        else:
            warnings.warn(
                "The `jinja2_coverage` plugin isn't loaded. You should enable it "
                "in your coverage configuration."
            )


class SimplatePlugin(coverage.plugin.CoveragePlugin):

    def __init__(self, options):
        self.website = import_object(options['website_object_path'])

    def file_tracer(self, filename):
        if filename.endswith('.spt'):
            return MultiTracer(filename, self._parse_simplate(filename))

    def file_reporter(self, filename):
        return MultiReporter(filename, self._parse_simplate(filename))

    def find_executable_files(self, src_dir):
        for root, dirs, files in os.walk(src_dir):
            for filename in files:
                if filename.endswith('.spt'):
                    yield os.path.join(root, filename)

    def _parse_simplate(self, filename):
        attach_coverage_plugins_to_renderer_factories()
        simplate = self.website.request_processor.resources.get(filename)
        with tokenize.open(filename) as f:
            source_code = f.read()
        pages = list(split(source_code))
        npages = len(pages)
        for page_number, page in enumerate(list(pages), start=1):
            if page.header:
                media_type, renderer_name = parse_specline(page.header)
                if media_type == '':
                    media_type = simplate.default_media_type
                if renderer_name == '':
                    renderer_name = simplate.defaults.renderers_by_media_type[media_type]
            elif page_number == 1 and npages > 1 or page_number == 2 and npages > 2:
                media_type, renderer_name = None, None
            else:
                media_type = simplate.default_media_type
                renderer_name = simplate.defaults.renderers_by_media_type[media_type]
            if renderer_name:
                renderer_factory = self.website.renderer_factories.get(renderer_name)
                is_python = (
                    getattr(renderer_factory, 'is_python', False) or
                    renderer_name in ('json_dump', 'jsonp_dump')
                )
                coverage_plugin = getattr(renderer_factory, 'coverage_plugin', None)
            else:
                renderer_factory = None
                is_python = True
                coverage_plugin = None
            if page.content:
                if coverage_plugin or is_python:
                    temp_file = NamedTemporaryFile(
                        dir=os.path.dirname(filename),
                        prefix='.', suffix=os.path.basename(filename),
                    )
                    temp_file.write(b'\n' * page.offset)
                    temp_file.write(escape(page.content).encode('utf8'))
                    temp_file.flush()
                    if coverage_plugin:
                        if callable(getattr(coverage_plugin, '_file_tracer', None)):
                            method_name = '_file_tracer'
                        else:
                            method_name = 'file_tracer'
                        tracer = getattr(coverage_plugin, method_name)(filename)
                        if not tracer:
                            warnings.warn(
                                f"{coverage_plugin.__class__.__name__}."
                                f"{method_name}({filename!r}) returned {tracer!r}"
                            )
                        reporter = coverage_plugin.file_reporter(temp_file.name)
                    else:
                        tracer = None
                        cov = coverage.Coverage._instances._last
                        assert cov, "Coverage object is missing"
                        reporter = coverage.python.PythonFileReporter(
                            temp_file.name, coverage=cov
                        )
                else:
                    warnings.warn(f"no coverage plugin found for {renderer_name} renderer")
                    tracer = temp_file = reporter = None
            else:
                tracer = temp_file = reporter = None
            pages[page_number - 1] = FilePage(
                page.offset + 1, page.content, is_python, tracer, temp_file, reporter,
            )
        return pages

    def sys_info(self):
        return [('version', __version__)]


class List(list):

    def append(self, obj):
        self._last = obj
        return super().append(obj)


assert coverage.Coverage._instances == []
coverage.Coverage._instances = List()


def coverage_init(reg, options):
    reg.add_file_tracer(SimplatePlugin(options))


add_file_tracers = coverage.sqldata.CoverageData.add_file_tracers

def _add_file_tracers(self, file_tracers):
    for filename in file_tracers:
        self._file_id(filename, add=True)
    return add_file_tracers(self, file_tracers)

coverage.sqldata.CoverageData.add_file_tracers = _add_file_tracers
