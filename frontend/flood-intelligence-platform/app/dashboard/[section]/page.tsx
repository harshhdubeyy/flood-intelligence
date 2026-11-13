import { CommandCenter, Section } from '../../../components/command-center';
export default async function Page({ params }: { params: Promise<{ section: string }> }) {
  const { section: requestedSection } = await params;
  const section = ['reports', 'alerts', 'social', 'responders'].includes(requestedSection)
    ? requestedSection as Section
    : 'map';
  return <CommandCenter section={section} />;
}
