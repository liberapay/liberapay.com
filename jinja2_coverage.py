from fnmatch import fnmatch
from functools import reduce
from importlib import import_module
import os
import sys

import coverage.plugin
from jinja2 import Environment


__version__ = '0.1'


plugin = None


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


def is_block_start(line: str, env: Environment) -> bool:
    """TODO
    """
    tokens = iter(line.split())
    first_token = next(tokens, None)
    second_token = next(tokens, None)
    if second_token == 'block':
        if first_token == env.line_statement_prefix:
            return True
        if first_token == env.block_start_string:
            if not next(tokens, None):
                # block name
                return False
            next_token = next(tokens, None)
            if next_token == 'scoped':
                next_token = next(tokens, None)
            if next_token == 'required':
                next_token = next(tokens, None)
            return (
                next_token == (env.block_end_string + env.block_start_string) and
                next(tokens, None) == 'endblock' and
                next(tokens, None) == env.block_end_string and
                next(tokens, None) is None
            )
    return False


class JinjaPlugin(coverage.plugin.CoveragePlugin):

    def __init__(self, options):
        self.environment = import_object(options['environment_path'])
        self.filename_patterns = (options.get('filename_patterns') or '*.html').split()

    def file_tracer(self, filename):
        for pattern in self.filename_patterns:
            if fnmatch(filename, pattern):
                return JinjaFileTracer(filename, self.environment)

    def _file_tracer(self, filename):
        return JinjaFileTracer(filename, self.environment)

    def file_reporter(self, filename):
        return JinjaFileReporter(filename, self.environment)

    def find_executable_files(self, src_dir):
        for root, dirs, files in os.walk(src_dir):
            for filename in files:
                for pattern in self.filename_patterns:
                    if fnmatch(filename, pattern):
                        yield os.path.join(root, filename)

    def sys_info(self):
        return [('version', __version__)]


class JinjaFileTracer(coverage.plugin.FileTracer):

    def __init__(self, filename, environment):
        self.filename = filename
        self.environment = environment

    def source_filename(self):
        return self.filename

    def line_number_range(self, frame):
        try:
            template = frame.f_globals["__jinja_template__"]
        except KeyError:
            return -1, -1
        try:
            reversed_debug_info_dict = template.reversed_debug_info_dict
        except AttributeError:
            reversed_debug_info_dict = template.reversed_debug_info_dict = {
                code_line: template_line for template_line, code_line in template.debug_info
            }
        lineno = reversed_debug_info_dict.get(frame.f_lineno, -1)
        return lineno, lineno


class JinjaFileReporter(coverage.plugin.FileReporter):

    #token_types_map = {
        ## TODO jinja2 tokens → coverage tokens
        #'com' # a comment
        #'key' # a keyword
        #'nam' # a name, or identifier
        #'num' # a number
        #'op' # an operator
        #'str' # a string literal
        #'ws' # some white space
        #'txt' # some other kind of text
    #}

    def __init__(self, filename, environment):
        super().__init__(filename)
        self.environment = environment
        i = 0
        for a, b in zip(os.getcwd(), self.filename):
            if a != b:
                break
            i += 1
        self.template = self.environment.get_template(self.filename[i:])

    def lines(self):
        return set(
            template_line for template_line, code_line in self.template.debug_info
        )

    def excluded_lines(self):
        with open(self.filename) as f:
            templates_lines = f.readlines()
        env = self.environment
        return set(
            template_line for template_line, code_line in self.template.debug_info
            if is_block_start(templates_lines[template_line - 1], env)
        )

    #def source_token_lines(self):
        #return super().source_token_lines()
        #source_code = self.source()
        #lines = [[] for i in range(len(source_code.count('\n')))]
        #tokens = self.environment._tokenize(source_code, self.filename)
        #for token in tokens:
            #if token.type is token.value:
                #token.type = 'keyword'
            #token_type = self.token_types_map.get(token.type)
            #if not token_type:
                #warnings.warn(f"encountered unknown token type {token.type!r}")
            #source_lines[token.lineno].append((token_type or 'txt', token.value))
        #source_code = self.environment.preprocess(source_code, self.filename)
        #tokens = self.environment.lexer.tokeniter(source_code, self.filename)
        #for lineno, token_type, value in tokens:
            #token_type = self.token_types_map.get(token_type)
            #source_lines[lineno].append((token_type or 'txt', value))
        #return lines


def coverage_init(reg, options):
    global plugin
    if not plugin:
        plugin = JinjaPlugin(options)
    reg.add_file_tracer(plugin)
