const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const { mathjax } = require('mathjax-full/js/mathjax.js');
const { TeX } = require('mathjax-full/js/input/tex.js');
const { SVG } = require('mathjax-full/js/output/svg.js');
const { liteAdaptor } = require('mathjax-full/js/adaptors/liteAdaptor.js');
const { RegisterHTMLHandler } = require('mathjax-full/js/handlers/html.js');

const outputDir = path.join(__dirname, 'equations');
fs.mkdirSync(outputDir, { recursive: true });

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const tex = new TeX({ packages: ['base', 'ams'] });
const svg = new SVG({ fontCache: 'none' });
const html = mathjax.document('', { InputJax: tex, OutputJax: svg });

const equations = [
  {
    name: 'dynamic_advection_diffusion.png',
    latex: String.raw`\frac{\partial C}{\partial t}+\mathbf{u}\cdot\nabla C = \nabla\cdot(K\nabla C)+S-(\lambda_{uv}+\lambda_{dep}+\lambda_{rain})C+R`,
  },
  {
    name: 'infection_probability.png',
    latex: String.raw`P_{inf}=I_{window}\left(1-\exp(-D/D_0)\right)`,
  },
];

async function main() {
  for (const equation of equations) {
    const node = html.convert(equation.latex, { display: true });
    const svgString = adaptor.outerHTML(node);
    await sharp(Buffer.from(svgString)).png({ quality: 100, density: 300 }).toFile(path.join(outputDir, equation.name));
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
