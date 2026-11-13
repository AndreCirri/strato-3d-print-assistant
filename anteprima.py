"""Anteprima del file originale, senza analisi, riparazioni o slicing."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory


def carica(contenuto, estensione):
    """Carica la mesh originale senza applicare analisi o riparazioni."""
    import numpy as np
    import trimesh
    estensione = estensione.lower().lstrip('.')
    if estensione in {'step', 'stp'}:
        import augura_addon
        if not augura_addon.disponibile():
            raise ValueError("Per l’anteprima STEP serve l’add-on augura.")
        with TemporaryDirectory(prefix='strato-anteprima-') as cartella:
            originale = Path(cartella) / f'modello.{estensione}'
            convertito = Path(cartella) / 'modello.stl'
            originale.write_bytes(contenuto)
            augura_addon.step_in_stl(originale, convertito)
            mesh = trimesh.load_mesh(convertito, force='mesh', process=False)
    elif estensione in {'stl', 'obj', '3mf'}:
        mesh = trimesh.load_mesh(BytesIO(contenuto), file_type=estensione,
                                 force='mesh', process=False)
    else:
        raise ValueError("Formato non supportato per l’anteprima.")

    if (not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces)
            or not np.isfinite(mesh.vertices).all()):
        raise ValueError("Il file non contiene una superficie 3D visualizzabile.")
    if float(mesh.extents.max()) <= 0:
        raise ValueError("Il modello ha dimensioni nulle.")
    return mesh


def crea(contenuto, estensione, trasformazione=None, sfondo='#f8f9fa', zoom=1):
    # Import pesanti solo dopo la selezione di un modello.
    import numpy as np
    import trimesh
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    mesh = carica(contenuto, estensione)
    if trasformazione is not None:
        mesh.apply_transform(np.array(trasformazione))
    dimensione = float(mesh.extents.max())
    if dimensione <= 0:
        raise ValueError("Il modello ha dimensioni nulle.")
    mesh.apply_translation(-mesh.bounds.mean(axis=0))
    mesh.apply_scale(1 / dimensione)
    if len(mesh.faces) > 12000:
        try:
            mesh = mesh.simplify_quadric_decimation(face_count=12000)
        except Exception:
            # Limite anche quando il decimatore non riesce a trattare la mesh.
            mesh = mesh.submesh([np.linspace(0, len(mesh.faces) - 1, 12000, dtype=int)],
                                append=True)

    luce = np.array([.35, -.45, .82])
    luce /= np.linalg.norm(luce)
    intensita = .55 + .45 * np.clip(mesh.face_normals @ luce, 0, 1)
    colori = np.column_stack([intensita * c for c in (.58, .64, .72)])
    occhio = np.array([np.cos(np.radians(25)) * np.cos(np.radians(-55)),
                       np.cos(np.radians(25)) * np.sin(np.radians(-55)), np.sin(np.radians(25))])
    visibili = mesh.face_normals @ occhio > 0
    fig = Figure(figsize=(6, 4), dpi=120, facecolor=sfondo)
    ax = fig.add_axes([0, 0, 1, 1], projection='3d', facecolor=sfondo)
    ax.add_collection3d(Poly3DCollection(mesh.triangles[visibili], facecolors=colori[visibili],
                                        edgecolors='none'))
    for imposta in (ax.set_xlim, ax.set_ylim, ax.set_zlim):
        imposta(-.6, .6)
    ax.set_box_aspect((1, 1, 1), zoom=zoom)
    ax.view_init(elev=25, azim=-55)
    ax.set_axis_off()
    immagine = BytesIO()
    FigureCanvasAgg(fig).print_png(immagine)
    return immagine.getvalue()
