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
    in {
      packages = forAllSystems ({ pkgs, system }:
        let
          py = pythonEnv pkgs;
          # sitePackages path varies by python version; py.sitePackages is e.g. lib/python3.12/site-packages
          pySite = "${py}/${py.sitePackages}";
        in {
          default = self.packages.${system}.corpus;
          corpus = pkgs.stdenvNoCC.mkDerivation {
            pname = "benchtoo";
            version = "0.2.1";
            src = ./.;
            nativeBuildInputs = [ py pkgs.poppler_utils ]
            ++ pkgs.lib.optional (pkgs ? pdf2djvu) pkgs.pdf2djvu;
            dontConfigure = true;
            buildPhase = ''
              runHook preBuild
              export PYTHONNOUSERSITE=1
              export PYTHONPATH=${pkgs.lib.escapeShellArg pySite}
              ${py}/bin/python3 -c "import numpy, PIL; print('numpy', numpy.__version__, 'PIL', PIL.__version__)"
              ${py}/bin/python3 generators/gen_synthetic.py --out "$PWD/out"
              ${py}/bin/python3 generators/gen_archives.py --corpus "$PWD/out"
              ${py}/bin/python3 generators/gen_documents.py --out "$PWD/out" --pages 40
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
              description = "Benchmark image fixtures (content-class matrix) for thumtoo pixel paths";
              license = licenses.gpl3Plus;
              platforms = platforms.unix;
            };
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
