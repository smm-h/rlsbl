{
  "name": "{{npmScope}}/{{binCommand}}",
  "version": "0.0.0",
  "description": "{{binCommand}} - distributed via npm",
  "bin": {
    "{{binCommand}}": "bin/index.js"
  },
  "optionalDependencies": {
    "{{npmScope}}/{{binCommand}}-linux-x64": "0.0.0",
    "{{npmScope}}/{{binCommand}}-linux-arm64": "0.0.0",
    "{{npmScope}}/{{binCommand}}-darwin-x64": "0.0.0",
    "{{npmScope}}/{{binCommand}}-darwin-arm64": "0.0.0",
    "{{npmScope}}/{{binCommand}}-win32-x64": "0.0.0",
    "{{npmScope}}/{{binCommand}}-win32-arm64": "0.0.0"
  },
  "license": "MIT"
}
