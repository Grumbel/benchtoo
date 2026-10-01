{
  description = "benchtoo — synthetic content-class corpus for thumtoo/biltoo benches";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f {
        inherit system;
        pkgs = import nixpkgs { inherit system; };
      });
      pythonEnv = pkgs:
        pkgs.python3.withPackages (ps: [
          ps.numpy
          ps.pillow
          ps.reportlab
        ]);

      mkCorpus = { pkgs, py, pySite, pname, version, buildScript }:
        pkgs.stdenvNoCC.mkDerivation {
          inherit pname version;
          src = ./.;
          nativeBuildInputs = [ py pkgs.poppler_utils ]
            ++ pkgs.lib.optional (pkgs ? pdf2djvu) pkgs.pdf2djvu;
          dontConfigure = true;
          buildPhase = ''
            runHook preBuild
            export PYTHONNOUSERSITE=1
            export PYTHONPATH=${pkgs.lib.escapeShellArg pySite}
            ${py}/bin/python3 -c "import numpy, PIL; print('numpy', numpy.__version__, 'PIL', PIL.__version__)"
            ${buildScript}
            runHook postBuild
          '';
          installPhase = ''
            runHook preInstall
            mkdir -p $out
            cp -a out/. $out/
            cp manifest/manifest.schema.json $out/manifest.schema.json
            runHook postInstall
          '';
          meta = with pkgs.lib; {
            description = "Benchmark fixtures for thumtoo/biltoo (benchtoo)";
            license = licenses.gpl3Plus;
            platforms = platforms.unix;
          };
        };
    in {
      packages = forAllSystems ({ pkgs, system }:
        let
          py = pythonEnv pkgs;
          pySite = "${py}/${py.sitePackages}";
        in {
          default = self.packages.${system}.corpus;

          # Full matrix (all classes, large sizes, 40-page PDF).
          corpus = mkCorpus {
            inherit pkgs py pySite;
            pname = "benchtoo";
            version = "0.3.0";
            buildScript = ''
              ${py}/bin/python3 generators/gen_synthetic.py --out "$PWD/out"
              ${py}/bin/python3 generators/gen_archives.py --corpus "$PWD/out"
              ${py}/bin/python3 generators/gen_documents.py --out "$PWD/out" --pages 40
              if command -v rar >/dev/null 2>&1; then
                ${py}/bin/python3 generators/gen_rar.py --corpus "$PWD/out" || true
              fi
            '';
          };

          # CI / flake check: small, fast.
          corpus-smoke = mkCorpus {
            inherit pkgs py pySite;
            pname = "benchtoo-smoke";
            version = "0.3.0";
            buildScript = ''
              ${py}/bin/python3 generators/gen_synthetic.py --out "$PWD/out" --no-large \
                --classes photo,bookpage,comic
              ${py}/bin/python3 generators/gen_archives.py --corpus "$PWD/out"
              ${py}/bin/python3 generators/gen_documents.py --out "$PWD/out" --pages 8
            '';
          };
        });

      apps = forAllSystems ({ pkgs, system }:
        let
          py = pythonEnv pkgs;
        in {
          generate = {
            type = "app";
            program = "${pkgs.writeShellScript "benchtoo-generate" ''
              set -euo pipefail
              out="''${1:-./out}"
              shift || true
              export PYTHONNOUSERSITE=1
              export PYTHONPATH=${pkgs.lib.escapeShellArg "${py}/${py.sitePackages}"}
              exec ${py}/bin/python3 ${./generators/gen_synthetic.py} --out "$out" "$@"
            ''}";
            meta.description = "Regenerate synthetic corpus (content classes) into a directory";
          };
        });
    };
}
