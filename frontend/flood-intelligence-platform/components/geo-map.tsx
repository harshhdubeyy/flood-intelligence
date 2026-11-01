'use client';
import 'mapbox-gl/dist/mapbox-gl.css';
import Map, { Source, Layer } from 'react-map-gl';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer } from '@deck.gl/layers';

type Props={data?:GeoJSON.FeatureCollection;onWardClick:(id:string)=>void};
export function GeoMap({data,onWardClick}:Props){
 const token=process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
 if(!token||!data) return null;
 const layers=[new GeoJsonLayer({id:'ward-risk',data,pickable:true,filled:true,stroked:true,getFillColor:[23,105,224,30],getLineColor:[23,105,224,175],lineWidthMinPixels:1,onClick:info=>{const id=String(info.object?.properties?.id??info.object?.properties?.ward_id??'');if(id)onWardClick(id)}})];
 return <DeckGL layers={layers} controller><Map mapboxAccessToken={token} initialViewState={{longitude:72.8777,latitude:19.0760,zoom:10}} mapStyle="mapbox://styles/mapbox/light-v11"><Source id="wards-outline" type="geojson" data={data}><Layer id="wards-outline-line" type="line" paint={{'line-color':'#1769e0','line-width':1,'line-opacity':.45}}/></Source></Map></DeckGL>;
}
