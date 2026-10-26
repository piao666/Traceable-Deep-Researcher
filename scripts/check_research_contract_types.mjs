/** Compile the shared Python/TypeScript wire fixture without writing a TS file. */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/nextjs/package.json'));
const ts = require('typescript');
const fixturePath = process.argv[2] ?? path.join(root, 'tests/fixtures/research-contract.v1.json');
const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
const virtualFile = path.join(root, 'frontend/nextjs/types/__m0_fixture_check__.ts');
const source = `import type { ResearchTaskRequest, TaskEvent, SubscribeCommand } from './research';
const fixture = ${JSON.stringify(fixture)} satisfies {
  request: ResearchTaskRequest; event: TaskEvent; subscribe: SubscribeCommand;
};\n`;
const options = {
  strict: true, noEmit: true, skipLibCheck: true, types: [],
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext,
  moduleResolution: ts.ModuleResolutionKind.Bundler,
};
const host = ts.createCompilerHost(options);
const originalGetSourceFile = host.getSourceFile.bind(host);
const normalize = value => path.resolve(value).toLowerCase();
host.getSourceFile = (name, languageVersion, onError, shouldCreateNewSourceFile) =>
  normalize(name) === normalize(virtualFile)
    ? ts.createSourceFile(name, source, languageVersion, true)
    : originalGetSourceFile(name, languageVersion, onError, shouldCreateNewSourceFile);
const program = ts.createProgram([virtualFile], options, host);
const diagnostics = ts.getPreEmitDiagnostics(program);
if (diagnostics.length) {
  process.stderr.write(ts.formatDiagnosticsWithColorAndContext(diagnostics, {
    getCanonicalFileName: value => value,
    getCurrentDirectory: () => root,
    getNewLine: () => '\n',
  }));
  process.exitCode = 1;
} else {
  process.stdout.write('Shared research contract fixture: TypeScript check passed.\n');
}
