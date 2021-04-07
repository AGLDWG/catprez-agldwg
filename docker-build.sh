CATPREZ_HOME=/Users/nick/Work/surround/CatPrez

# copy my data to CatPrez
mv $CATPREZ_HOME/catprez/data $CATPREZ_HOME/catprez/data-orig
mkdir $CATPREZ_HOME/catprez/data
cp -r data $CATPREZ_HOME/catprez

# run Docker there
docker build -t catprez-agldwg -f $CATPREZ_HOME/Dockerfile $CATPREZ_HOME

# clean-up
#rm -r $CATPREZ_HOME/catprez/data/
#mv $CATPREZ_HOME/catprez/data-orig $CATPREZ_HOME/catprez/data

echo "complete"