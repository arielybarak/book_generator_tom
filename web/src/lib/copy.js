/**
 * Central Hebrew copy. Plain, warm, no jargon (see the glossary in web/CLAUDE.md).
 * Keeping strings here keeps tone consistent and makes wording easy to tune.
 */
export const COPY = {
  appName: 'TOM',
  tagline: 'יוצרים ספרי מישוש לילדים',

  steps: ['פתיחה', 'בניית הספר', 'יצירה', 'הורדה'],

  landing: {
    headline: 'הופכים משפט לעמוד שאפשר לגעת בו',
    sub: 'כותבים משפט בעברית, מתארים את הציור — ומקבלים עמוד מוכן להדפסה בתלת־ממד, עם ציור בולט, טקסט וברייל. בלי שום ידע טכני.',
    cta: 'בואו ניצור ספר',
    note: 'מתאים להורים, גננות וכל מי שרוצה לספר סיפור במגע.',
    galleryTitle: 'כך נראה עמוד גמור',
  },

  builder: {
    title: 'בנו את הספר שלכם',
    bookNameLabel: 'איך נקרא לספר?',
    bookNamePlaceholder: 'למשל: עמי ותמי',
    sentenceLabel: 'מה כתוב בעמוד?',
    sentencePlaceholder: 'כתבו משפט קצר בעברית…',
    pictureLabel: 'מה רואים בציור?',
    picturePlaceholder: 'תארו במילה־שתיים, למשל: כלב, בית, פרח',
    addPage: 'הוסיפו עמוד',
    pagesTitle: 'העמודים בספר',
    empty: 'עוד לא הוספתם עמודים',
    generate: 'יוצרים את הספר',
    soundQuestion: 'איך הוגים?',
  },

  generate: {
    working: 'מציירים את העמוד… רגע אחד',
    waking: 'המנוע מתעורר — זה לוקח רגע בפעם הראשונה',
    page: 'עמוד',
    regenerate: 'ציירו מחדש',
    next: 'אהבתי, ממשיכים',
    failed: 'משהו השתבש ביצירת העמוד. אפשר לנסות שוב.',
    noStl: 'הציור מוכן, אך קובץ ההדפסה נכשל. אפשר לצייר מחדש.',
    allReady: 'כל העמודים מוכנים להורדה',
    backToEdit: 'חזרה לעריכה',
    retry: 'נסו שוב',
  },

  download: {
    title: 'העמוד מוכן!',
    sub: 'אפשר לסובב את הדגם ולראות איך ייראה במגע, ואז להוריד את הקובץ להדפסה.',
    download: 'הורידו את הקובץ להדפסה',
    printTitle: 'איך מדפיסים?',
    printBody:
      'הקובץ הוא קובץ הדפסה תלת־ממדית (STL). אפשר להדפיס במדפסת תלת־ממד ביתית, או לשלוח לבית דפוס/מעבדת הדפסה תלת־ממדית שיכינו אותו עבורכם.',
    startOver: 'יוצרים ספר חדש',
  },

  common: {
    back: 'חזרה',
    remove: 'מחיקה',
    of: 'מתוך',
  },
}
