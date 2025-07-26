from pathlib import Path

def scan_container_files(directory):
    """Scan the container directory for Containerfile and *.containerfile files."""
    container_files = [f.name for f in Path(directory).iterdir() if f.is_file() and (f.name.endswith('.containerfile') or f.name == 'Containerfile')]
    return container_files

def determine_dependencies(container_files):
    """Determine dependencies based on the `FROM` line in the file content."""
    dependencies = {}
    for file in container_files:
        file_path = Path(__file__).parent / file
        with open(file_path, 'r') as f:
            for line in f:
                if line.startswith('FROM'):
                    base_image = line.split()[1].strip()
                    # common prefix: ghcr.io/clamsproject/clams-python
                    # common suffix: :#clams_version
                    # just get the middle 
                    base_image = base_image[len("ghcr.io/clamsproject/clams-python"):-len(":#clams_version")]
                    if len(base_image) == 0:
                        dependencies[file] = []
                    else:
                        dependencies[file] = base_image.split('-')[1:]  # assuming suffix starts with a dash
                    break
    for k in sorted(dependencies.keys()):
        print(f"{k}: {dependencies[k]}")  # Debugging output to check dependencies
    return dependencies

def generate_workflow(container_files, dependencies, output_file):
    """Generate the containers.yml workflow file."""
    with open(output_file, 'w') as f:
        # Add a comment indicating the file is auto-generated
        f.write("# This file is auto-generated. Do not edit manually.\n\n")

        # Write the static configuration part
        f.write("name: \"📦 Publish (base images)\"\n\n")
        f.write("on:\n  push:\n    tags:\n      - '[0-9]+.[0-9]+.[0-9]+'\n  workflow_dispatch:\n    inputs:\n      version:\n        description: 'version to tag images'\n        required: true\n\n")
        f.write("jobs:\n")
        f.write("  set-version:\n")
        f.write("    runs-on: ubuntu-latest\n")
        f.write("    name: \"🏷 Set version value\"\n")
        f.write("    outputs:\n")
        f.write("      version: ${{ steps.output_version.outputs.version }}\n")
        f.write("    steps:\n")
        f.write("    - name: \"📌 Set VERSION value from dispatch inputs\"\n")
        f.write("      id: get_version_dispatch\n")
        f.write("      if: ${{ github.event_name == 'workflow_dispatch' }}\n")
        f.write("      run: echo \"VERSION=${{ github.event.inputs.version }}\" >> $GITHUB_ENV\n")
        f.write("    - name: \"📌 Set VERSION value from pushed tag\"\n")
        f.write("      id: get_version_tag\n")
        f.write("      if: ${{ github.event_name == 'push' }}\n")
        f.write("      run: echo \"VERSION=$(echo \"${{ github.ref }}\" | cut -d/ -f3)\" >> $GITHUB_ENV\n")
        f.write("    - name: \"🏷 Record VERSION for follow-up jobs\"\n")
        f.write("      id: output_version\n")
        f.write("      run: |\n")
        f.write("        echo \"version=${{ env.VERSION }}\" >> $GITHUB_OUTPUT\n")
        f.write("  check-deployment:\n")
        f.write("    name: \"✅ PyPI deployment check\"\n")
        f.write("    runs-on: ubuntu-latest\n")
        f.write("    needs: ['set-version']\n")
        f.write("    steps:\n")
        f.write("    - name: \"⏱️ Wait up to 20 minutes for the new clams-python is deployed on PyPI\"\n")
        f.write("      uses: nev7n/wait_for_response@v1\n")
        f.write("      with:\n")
        f.write("        url: \"https://pypi.org/project/clams-python/${{ needs.set-version.outputs.version }}/\"\n")
        f.write("        responseCode: 200\n")
        f.write("        timeout: 1200000\n")
        f.write("        interval: 5000\n")

        # Sort jobs: base first, then by dependency length and filename
        sorted_files = sorted(container_files, key=lambda x: (x != 'Containerfile', len(dependencies.get(x, [])), '-'.join(dependencies.get(x, [])), x))

        for file in sorted_files:
            job_name = 'base' if file == 'Containerfile' else file.replace('.containerfile', '')
            f.write(f"\n  call-build-{job_name}:\n")
            human_friendly_job_name = "the base" if job_name == 'base' else f"`{job_name}`"
            f.write(f"    name: \"🤙 Call container workflow with {human_friendly_job_name}\"\n")
            dependency_job = dependencies.get(file, None)
            print(job_name, dependency_job)
            if len(dependency_job) > 0:
                f.write(f"    needs: ['set-version', 'call-build-{'-'.join(dependency_job)}']\n")
            else:
                if job_name == 'base':
                    f.write(f"    needs: ['set-version', 'check-deployment']\n")
                else:
                    f.write(f"    needs: ['set-version', 'call-build-base']\n")
            f.write("    uses: ./.github/workflows/container.yml\n")
            f.write("    secrets: inherit\n")
            f.write("    with:\n")
            f.write(f"      buildfilename: './container/{file}'\n")
            f.write(f"      version: ${{{{ needs.set-version.outputs.version }}}}\n")

if __name__ == "__main__":
    container_dir = Path(__file__).parent
    output_file = Path(__file__).parent.parent / ".github/workflows/containers.yml"

    print("Scanning container directory...")
    container_files = scan_container_files(container_dir)

    print("Determining dependencies...")
    dependencies = determine_dependencies(container_files)

    print("Generating workflow file...")
    generate_workflow(container_files, dependencies, output_file)

    print(f"Workflow file generated at {output_file}")
