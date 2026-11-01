import { CommandCenter, Section } from '../../../components/command-center';
export default function Page({params}:{params:{section:string}}){ const section = ['reports','alerts','social','responders'].includes(params.section) ? params.section as Section : 'map'; return <CommandCenter section={section}/> }
