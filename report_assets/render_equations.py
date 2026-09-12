from pathlib import Path
import matplotlib.pyplot as plt


OUTPUT = Path(__file__).resolve().parent / 'equations'
OUTPUT.mkdir(exist_ok=True)

EQUATIONS = [
    (
        'field_to_map.png',
        r'$\mathbf{p}_{map}=R(\theta)\,\mathbf{p}_{field}+\mathbf{t},\qquad \mathbf{t}=[t_x,t_y]^{\mathsf{T}}$',
        18,
    ),
    (
        'sampling_coverage.png',
        r'$c_q(g)=\max\left(0,1-\frac{d(q,g)^2}{R^2}\right),\qquad C_S(g)=\max_{q\in S}c_q(g)$',
        18,
    ),
    (
        'gaussian_plume.png',
        r'$C(x,y,z)=\frac{Q}{2\pi u\sigma_y\sigma_z}\exp\left(-\frac{y^2}{2\sigma_y^2}\right)\left[\exp\left(-\frac{(z-H)^2}{2\sigma_z^2}\right)+\exp\left(-\frac{(z+H)^2}{2\sigma_z^2}\right)\right]$',
        13,
    ),
    (
        'dynamic_advection_diffusion.png',
        r'$\frac{\partial C}{\partial t}+\mathbf{u}\cdot\nabla C = \nabla\cdot(K\nabla C)+S-(\lambda_{uv}+\lambda_{dep}+\lambda_{rain})C+R$',
        15,
    ),
    (
        'infection_probability.png',
        r'$P_{inf}=I_{window}\left(1-\exp(-D/D_0)\right)$',
        18,
    ),
]


for name, formula, size in EQUATIONS:
    fig = plt.figure(figsize=(8.0, 0.78), dpi=300, facecolor='white')
    fig.text(0.5, 0.5, formula, fontsize=size, ha='center', va='center', color='black')
    plt.axis('off')
    fig.savefig(OUTPUT / name, dpi=300, bbox_inches='tight', pad_inches=0.08, facecolor='white')
    plt.close(fig)
