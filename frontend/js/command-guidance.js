// Only names present in the 29-SEP-2026 manual receive manual-based guidance.
const manualFamilies = [
  {tanks:['01','03','05','07','10','12','14'], endpoints:['DoorOpenRemote','DoorCloseRemote']},
  {tanks:['01','02','03','04','05','06','07','09','10','11','12','13','14','15','16'], endpoints:['FillWaterOn','FillWaterAuto']},
  {tanks:['02','04','06','07','08','09','12','15','16'], endpoints:['AirAgitationOn','AirAgitationAuto']},
  {tanks:['07'], endpoints:['CoolerOn','CoolerAuto','RectRemote']},
  {tanks:['01','03','05','07','10','14','16'], endpoints:['FilterRemote']},
  {tanks:['01','03','05','10','13','14','16'], endpoints:['HeaterRemote']},
  {tanks:['01'], endpoints:['USRemote']},
  {tanks:['03','05','10','14'], endpoints:['SwingRemote']},
  {tanks:['11'], endpoints:['SprayRemote']},
];

export function commandGuidance(tag) {
  const name = tag?.tag_name ?? '';
  const [, tank, endpoint] = /^Tank(\d{2})_(.+)$/.exec(name) ?? [];
  const manual = tag?.read_write === 'W' && tag.data_type === 'Bool' && (name === 'MainInlet' ||
    manualFamilies.some(group => group.tanks.includes(tank) && group.endpoints.includes(endpoint)));
  if (manual && endpoint?.startsWith('Door')) {
    const confirmed = tank === '01' && tag.device_address === (endpoint === 'DoorOpenRemote' ? 'M300' : 'M301');
    return {kind:'reset', confirmed, title:confirmed ? 'Manual reset after completion' : 'Door command: reset rule unconfirmed',
      evidence:confirmed ? 'Operator confirmed this rule for Tank 01 at M300/M301. The manual does not specify this rule.' : 'The manual identifies door commands and position feedback. This command’s hold/reset procedure remains unconfirmed.',
      one:confirmed ? 'Hold 1 while the door moves.' : 'Remote movement request. The required hold duration is unconfirmed.',
      zero:confirmed ? 'Send 0 after physical movement finishes.' : 'Confirm the clear procedure before you send 0.',
      procedure:confirmed ? 'After you manually send 0, check a fresh later readback of 0. The console does not reset the command automatically.' : 'Confirm this command’s procedure before testing. Tank 01 tests do not confirm other commands or addresses.'};
  }
  if (manual && (name === 'MainInlet' || endpoint.endsWith('On'))) {
    return {kind:'hold', hint:'hold', title:'Hold candidate: Always On request',
      evidence:'Maintained request inferred from the manual’s Always On description. The manual does not specify PLC hold/reset logic.',
      one:'An ON request is intended. Keeping 1 is a working interpretation.',
      zero:'Value 0 may withdraw the ON request. This does not guarantee that equipment stops.',
      procedure:'Confirm the command rule. If the rule requires holding 1, select Hold 1 before you send 1. The console records Keep at 1 after API acceptance and a fresh later readback of 1. It does not send another write. Send 0 when the confirmed procedure requires it.'};
  }
  if (manual && endpoint.endsWith('Auto')) {
    return {kind:'hold', title:'Hold candidate: mode selection',
      evidence:'The manual describes an Auto setting. The 1/0 polarity and mode interactions remain unconfirmed.',
      one:'Mode selection bit. Do not assume 1 enables Auto without confirmation.',
      zero:'Alternate bit value. Do not assume 0 stops the equipment.',
      procedure:'Confirm both mode values before testing. Select Hold 1 before sending only if 1 should remain selected. The console records your choice after API acceptance and a fresh later readback of 1. It does not send another write.'};
  }
  if (manual && endpoint.endsWith('Remote')) {
    return {kind:'hold', hint:'hold', title:'Hold candidate: Remote On request',
      evidence:'Maintained run/enable request inferred from the manual’s Remote On description. The request still needs supplier confirmation.',
      one:'The run/enable request is inferred. The required hold duration is unconfirmed.',
      zero:'The meaning of request-clear is unconfirmed. Value 0 does not guarantee that equipment stops.',
      procedure:'Confirm the command rule. If the rule requires holding 1, select Hold 1 before you send 1. The console records Keep at 1 after API acceptance and a fresh later readback of 1. It does not send another write. Send 0 when the confirmed procedure requires it.'};
  }
  return {kind:'unconfirmed', confirmed:false, title:'Hold/reset rule unconfirmed',
    evidence:'The manual does not establish a hold, pulse or reset rule for RemoteStart or unknown commands.',
    one:'Writing 1 does not establish its trigger or hold behavior.',
    zero:'Writing 0 does not establish its reset or stop behavior.',
    procedure:'Obtain the command rule before testing. Holding 1 for a non-door tag is an operator choice. The console does not recommend it. Select Hold 1 before you send 1. The console does not send automatic pulses, clears, or retries.'};
}
