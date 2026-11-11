"""Vista 3D locale: la mesh visualizzata non modifica i file di stampa."""
import hashlib
import json

import numpy as np
import streamlit as st

from anteprima import carica

SFONDO = '#0f172a'
COLORI = ['#94a3b8', '#ed686d', '#ff6827', '#ad83ed']
FACCE_MAX = 30000


@st.cache_data(show_spinner=False, max_entries=12)
def prepara(contenuto, estensione, trasformazione=None, supporti=False):
    mesh = carica(contenuto, estensione)
    if trasformazione is not None:
        mesh.apply_transform(np.asarray(trasformazione))
    mesh.merge_vertices()
    ridotta = len(mesh.faces) > FACCE_MAX
    if ridotta:
        mesh = mesh.simplify_quadric_decimation(face_count=FACCE_MAX)
    centro = mesh.bounds.mean(axis=0)
    mesh.apply_translation([-centro[0], -centro[1], -mesh.bounds[0, 2]])
    colori = None
    if supporti:
        from analisi import classifica_facce
        tipo, _, _ = classifica_facce(mesh)
        colori = np.asarray(COLORI)[tipo].tolist()
    matrice = np.asarray(trasformazione).tolist() if trasformazione is not None else None
    revisione = hashlib.sha256(contenuto + json.dumps(matrice).encode()).hexdigest()
    return dict(vertici=mesh.vertices.copy(), facce=mesh.faces.copy(), colori=colori,
                limiti=mesh.bounds.copy(), ridotta=ridotta, revisione=revisione)


def figura(dati):
    import plotly.graph_objects as go

    v, f = dati['vertici'], dati['facce']
    lo, hi = dati['limiti']
    dimensione = float((hi - lo).max())
    raggio = dimensione * .75
    passo_base = 10 ** np.floor(np.log10(dimensione / 8))
    passo = next(passo_base * m for m in (1, 2, 5, 10) if passo_base * m >= dimensione / 8)
    gx, gy, gz = [], [], []
    for q in np.arange(-np.floor(raggio / passo), np.floor(raggio / passo) + 1) * passo:
        gx += [-raggio, raggio, None, q, q, None]
        gy += [q, q, None, -raggio, raggio, None]
        gz += [0, 0, None, 0, 0, None]
    fig = go.Figure()
    fig.add_trace(go.Scatter3d(x=gx, y=gy, z=gz, mode='lines',
                              line=dict(color='#334155', width=1), hoverinfo='skip', showlegend=False))
    # Luce nello spazio del modello, coerente anche tra browser/WebGL diversi.
    triangoli = v[f]
    normali = np.cross(triangoli[:, 1] - triangoli[:, 0], triangoli[:, 2] - triangoli[:, 0])
    normali /= np.maximum(np.linalg.norm(normali, axis=1, keepdims=True), 1e-12)
    luce = np.array([.35, -.45, .82])
    luce /= np.linalg.norm(luce)
    intensita = .45 + .55 * np.clip(normali @ luce, 0, 1)
    basi = dati['colori'] or [COLORI[0]] * len(f)
    rgb = np.array([[int(c[n:n + 2], 16) for n in (1, 3, 5)] for c in basi])
    rgb = np.clip(rgb * intensita[:, None], 0, 255).astype(int)
    colori = [f'#{r:02x}{g:02x}{b:02x}' for r, g, b in rgb]
    fig.add_trace(go.Mesh3d(x=v[:, 0].tolist(), y=v[:, 1].tolist(), z=v[:, 2].tolist(),
                           i=f[:, 0].tolist(), j=f[:, 1].tolist(), k=f[:, 2].tolist(),
                           facecolor=colori, flatshading=True,
                           lighting=dict(ambient=1, diffuse=0, specular=0),
                           hoverinfo='skip', name='Modello', showlegend=False))
    origine = np.array([-raggio * .85, -raggio * .85, 0.])
    for indice, (nome, colore) in enumerate(zip('XYZ', ('#8ab9d4', '#85c6ae', '#c4cbd0'))):
        fine = origine.copy()
        fine[indice] += dimensione * .18
        fig.add_trace(go.Scatter3d(x=[origine[0], fine[0]], y=[origine[1], fine[1]], z=[origine[2], fine[2]],
                                  mode='lines+text', text=['', nome], textposition='top center',
                                  textfont=dict(family='Plus Jakarta Sans', size=10, color=colore), line=dict(color=colore, width=2),
                                  hoverinfo='skip', showlegend=False))
    asse = dict(visible=False, showbackground=False, showspikes=False)
    fig.update_layout(
        font=dict(family='Plus Jakarta Sans', color='#94a3b8'),
        paper_bgcolor=SFONDO, plot_bgcolor=SFONDO, margin=dict(l=0, r=0, t=0, b=0),
        height=320, showlegend=False, uirevision=dati['revisione'],
        scene=dict(bgcolor=SFONDO, aspectmode='data', dragmode='orbit',
                   xaxis={**asse, 'range': [-raggio, raggio]},
                   yaxis={**asse, 'range': [-raggio, raggio]},
                   zaxis={**asse, 'range': [-dimensione * .03, max(hi[2], dimensione * .25)]},
                   camera=dict(up=dict(x=0, y=0, z=1), eye=dict(x=1.2, y=-1.4, z=1.0),
                               projection=dict(type='orthographic'))))
    return fig


def mostra(contenuto, estensione, *, key, trasformazione=None, supporti=False):
    dati = prepara(contenuto, estensione, trasformazione, supporti)
    fig = figura(dati)
    st.plotly_chart(fig, key=key, width='stretch', height='stretch', theme=None,
                    config=dict(displaylogo=False, scrollZoom=True,
                                modeBarButtonsToRemove=['toImage', 'resetCameraLastSave3d']))
    if dati['ridotta']:
        st.caption('Anteprima alleggerita. Il modello originale resta invariato.')
